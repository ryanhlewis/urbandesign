import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';

// Deck.GL + react-map-gl/maplibre
import DeckGL from '@deck.gl/react';
import {ScatterplotLayer, GeoJsonLayer} from '@deck.gl/layers';
import {Map} from 'react-map-gl/maplibre';

// Turf for buffering, difference, point-in-polygon
import * as turf from '@turf/turf';

// Lucide icons
import {Loader2, Check, X} from 'lucide-react';

// Data URLs
const TAXI_CSV_URL =
  'https://raw.githubusercontent.com/keplergl/kepler.gl-data/master/nyctrips/data.csv';

const BIDS_GEOJSON_URL =
  'https://data.cityofnewyork.us/resource/7jdm-inj8.geojson';

// NTA boundary polygons for all boroughs (we'll filter Manhattan)
const NTA_GEOJSON_URL =
  'https://raw.githubusercontent.com/nycehs/NYC_geography/refs/heads/master/NTA.geo.json';

// Types
type TaxiTrip = {
  pickup: [number, number];
  dropoff: [number, number];
};

type IntersectionStats = {
  totalTrips: number;
  pickupInBID: number;
  dropoffInBID: number;
  elapsedMs: number;
};

const INITIAL_VIEW_STATE = {
  longitude: -73.99,
  latitude: 40.75,
  zoom: 11,
  pitch: 0,
  bearing: 0
};

export default function App() {
  // -----------------------------
  // State
  // -----------------------------
  const [taxiData, setTaxiData] = useState<TaxiTrip[]>([]);
  const [rawBids, setRawBids] = useState<turf.FeatureCollection | null>(null);

  // Manhattan polygons as an array (Polygon or MultiPolygon)
  const [manhattanArray, setManhattanArray] = useState<turf.Feature[]>([]);

  // Final BIDs after buffering (and possibly subtracting Manhattan)
  const [bufferedBids, setBufferedBids] = useState<turf.FeatureCollection | null>(null);

  // UI states
  const [bufferDistance, setBufferDistance] = useState<number>(0);
  const [manhattanEnabled, setManhattanEnabled] = useState(true);
  const [isComputing, setIsComputing] = useState(false);
  const [intersectionStats, setIntersectionStats] = useState<IntersectionStats | null>(
    null
  );

  // -----------------------------
  // 1) Load Taxi CSV
  // -----------------------------
  useEffect(() => {
    async function loadTaxiData() {
      try {
        const resp = await fetch(TAXI_CSV_URL);
        const csvText = await resp.text();
        const lines = csvText.trim().split('\n');
        const header = lines[0].split(',');

        const pickupLonIdx = header.indexOf('pickup_longitude');
        const pickupLatIdx = header.indexOf('pickup_latitude');
        const dropoffLonIdx = header.indexOf('dropoff_longitude');
        const dropoffLatIdx = header.indexOf('dropoff_latitude');

        const trips: TaxiTrip[] = [];
        for (let i = 1; i < lines.length; i++) {
          const row = lines[i].split(',');
          if (row.length < header.length) continue;

          const pickupLon = parseFloat(row[pickupLonIdx]);
          const pickupLat = parseFloat(row[pickupLatIdx]);
          const dropLon = parseFloat(row[dropoffLonIdx]);
          const dropLat = parseFloat(row[dropoffLatIdx]);

          // skip nonsense coords
          if (
            Math.abs(pickupLon) < 1 ||
            Math.abs(pickupLat) < 1 ||
            Math.abs(dropLon) < 1 ||
            Math.abs(dropLat) < 1
          ) {
            continue;
          }

          trips.push({
            pickup: [pickupLon, pickupLat],
            dropoff: [dropLon, dropLat]
          });
        }

        setTaxiData(trips);
      } catch (err) {
        console.error('Error loading taxi data:', err);
      }
    }
    loadTaxiData();
  }, []);

  // -----------------------------
  // 2) Load BIDs
  // -----------------------------
  useEffect(() => {
    async function loadBIDs() {
      try {
        const resp = await fetch(BIDS_GEOJSON_URL);
        const data = await resp.json();
        setRawBids(data);
      } catch (err) {
        console.error('Error loading BIDs:', err);
      }
    }
    loadBIDs();
  }, []);

  // -----------------------------
  // 3) Load Manhattan polygons as array
  // -----------------------------
  useEffect(() => {
    async function loadManhattan() {
      try {
        const resp = await fetch(NTA_GEOJSON_URL);
        const data = await resp.json();

        // Filter for "Manhattan" + geometry=Polygon/MultiPolygon
        const manhattanPolys: turf.Feature[] = data.features.filter((feat: any) => {
          if (feat.properties?.BoroName !== 'Manhattan') return false;
          const t = feat.geometry?.type;
          return t === 'Polygon' || t === 'MultiPolygon';
        });

        setManhattanArray(manhattanPolys);
      } catch (err) {
        console.error('Error loading Manhattan boundary:', err);
      }
    }
    loadManhattan();
  }, []);

  // -----------------------------
  // 4) Buffer & Exclude Manhattan
  //    single effect
  // -----------------------------
  useEffect(() => {
    if (!rawBids) {
      setBufferedBids(null);
      return;
    }

    // 1) Buffer BIDs
    let newFeatures: turf.Feature[] = rawBids.features.map((feat) => {
      // skip non-polygon
      if (
        feat.geometry?.type !== 'Polygon' &&
        feat.geometry?.type !== 'MultiPolygon'
      ) {
        return null; // skip
      }

      if (bufferDistance > 0) {
        try {
          return turf.buffer(feat, bufferDistance, {units: 'meters'});
        } catch {
          return null;
        }
      }
      return feat; // no buffer
    });

    // remove null
    newFeatures = newFeatures.filter(Boolean);

    // 2) If Manhattan is disabled => subtract each Manhattan poly
    if (!manhattanEnabled && manhattanArray.length > 0) {
      for (const manFeat of manhattanArray) {
        const next: turf.Feature[] = [];
        for (const bidFeat of newFeatures) {
          try {
            const diff = turf.difference(bidFeat, manFeat);
            if (diff) next.push(diff);
            // if null => fully inside Manhattan => skip
          } catch (err) {
            console.warn('Difference error, skipping feature:', err);
            // Keep original shape if difference fails
            next.push(bidFeat);
          }
        }
        newFeatures = next;
      }
    }

    // 3) final feature collection
    setBufferedBids(turf.featureCollection(newFeatures));
  }, [rawBids, manhattanArray, manhattanEnabled, bufferDistance]);

  // -----------------------------
  // 5) Intersection Stats
  // -----------------------------
  async function handleIntersect() {
    if (!bufferedBids || taxiData.length === 0) return;

    setIsComputing(true);
    // Let the UI show spinner
    await new Promise((r) => setTimeout(r, 0));

    const t0 = performance.now();
    let pickupInBID = 0;
    let dropoffInBID = 0;
    const feats = bufferedBids.features;

    for (const trip of taxiData) {
      const pickupPt = turf.point(trip.pickup);
      const dropoffPt = turf.point(trip.dropoff);

      // check each polygon
      const inPickup = feats.some((f) => turf.booleanPointInPolygon(pickupPt, f));
      if (inPickup) pickupInBID++;

      const inDrop = feats.some((f) => turf.booleanPointInPolygon(dropoffPt, f));
      if (inDrop) dropoffInBID++;
    }
    const t1 = performance.now();

    setIntersectionStats({
      totalTrips: taxiData.length,
      pickupInBID,
      dropoffInBID,
      elapsedMs: t1 - t0
    });
    setIsComputing(false);
  }

  // -----------------------------
  // 6) Deck.GL layers
  // -----------------------------
  const bidsLayer = new GeoJsonLayer({
    id: 'bids-layer',
    data: bufferedBids || undefined,
    filled: true,
    stroked: true,
    getLineColor: [255, 0, 255],
    getFillColor: [255, 0, 255, 60],
    lineWidthMinPixels: 1
  });

  // If Manhattan is disabled, display a red overlay for the Manhattan polygons
  const manhattanLayer =
    !manhattanEnabled && manhattanArray.length
      ? new GeoJsonLayer({
          id: 'manhattan-layer',
          data: turf.featureCollection(manhattanArray),
          filled: true,
          stroked: true,
          getLineColor: [150, 0, 0],
          getFillColor: [150, 0, 0, 70],
          lineWidthMinPixels: 2
        })
      : null;

  const pickupLayer = new ScatterplotLayer({
    id: 'pickup-layer',
    data: taxiData,
    getPosition: (d) => d.pickup,
    getFillColor: [255, 0, 0],
    radiusScale: 30,
    radiusMinPixels: 1
  });

  const dropoffLayer = new ScatterplotLayer({
    id: 'dropoff-layer',
    data: taxiData,
    getPosition: (d) => d.dropoff,
    getFillColor: [0, 255, 0],
    radiusScale: 30,
    radiusMinPixels: 1
  });

  const layers = [bidsLayer, manhattanLayer, pickupLayer, dropoffLayer].filter(Boolean);

  // -----------------------------
  // 7) Render
  // -----------------------------
  return (
    <div className="relative w-full h-full">
      {/* Control Panel */}
      <div className="absolute top-4 left-4 z-50 bg-white shadow-lg rounded-lg p-4 w-80 space-y-4">
        <h1 className="text-lg font-bold text-gray-700 flex items-center gap-2">
          Taxi Rides vs BIDs
        </h1>

        {/* Buffer Distance Slider */}
        <div className="flex flex-col space-y-1">
          <label className="text-sm text-gray-600 font-medium">
            Buffer distance (meters)
          </label>
          <input
            type="range"
            min={0}
            max={300}
            step={10}
            value={bufferDistance}
            onChange={(e) => setBufferDistance(Number(e.target.value))}
            className="accent-pink-500"
          />
          <span className="text-sm text-gray-800">
            {bufferDistance} m
          </span>
        </div>

        <div className="flex items-center space-x-4">

        {/* Manhattan Toggle */}
        <button
          onClick={() => setManhattanEnabled(!manhattanEnabled)}
          className="flex items-center gap-2 px-3 py-2 rounded-md border border-pink-400 text-pink-500 hover:bg-pink-50 transition-colors"
        >
          {manhattanEnabled ? (
            <>
              <Check className="w-4 h-4" />
              <span>Manhattan</span>
            </>
          ) : (
            <>
              <X className="w-4 h-4" />
              <span>Manhattan</span>
            </>
          )}
        </button>

        {/* Intersect Button */}
        <button
          onClick={handleIntersect}
          disabled={!bufferedBids || !taxiData.length}
          className="flex items-center justify-center gap-2 px-3 py-2 bg-pink-500 text-white rounded-md disabled:bg-gray-300"
        >
          {isComputing ? (
            <>
              <Loader2 className="animate-spin w-5 h-5" />
              <span>Computing...</span>
            </>
          ) : (
            <span>Intersect</span>
          )}
        </button>

        </div>

        {/* Intersection Stats */}
        {intersectionStats && !isComputing && (
          <div className="border-t border-gray-200 pt-2 mt-2 text-sm text-gray-800 space-y-1">
            <div>
              <b>Total Trips:</b> {intersectionStats.totalTrips}
            </div>
            <div>
              <b>Pickup in BIDs:</b>{' '}
              {(
                (intersectionStats.pickupInBID / intersectionStats.totalTrips) *
                100
              ).toFixed(1)}
              %
            </div>
            <div>
              <b>Dropoff in BIDs:</b>{' '}
              {(
                (intersectionStats.dropoffInBID / intersectionStats.totalTrips) *
                100
              ).toFixed(1)}
              %
            </div>
            <div>
              <b>Time:</b> {intersectionStats.elapsedMs.toFixed(0)} ms
            </div>
          </div>
        )}
      </div>

      {/* DeckGL + Map */}
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller={true}
        layers={layers}
        style={{width: '100%', height: '100%'}}
      >
        <Map
          reuseMaps
          mapStyle="https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json"
        />
      </DeckGL>
    </div>
  );
}

// The function called from index.html
export function renderToDOM(container: HTMLElement | null) {
  if (!container) return;
  createRoot(container).render(<App />);
}
