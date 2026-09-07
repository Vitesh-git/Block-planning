import { useEffect, useState, useCallback } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip as LTooltip } from 'react-leaflet'
import { Dashboard } from '../api/client'
import Header from '../components/Header.jsx'
import { corridorLatLngs, STATION_COORDS, STATUS_COLOR } from '../utils/geo'

// Railway corridor map with per-corridor maintenance status colouring (Leaflet).
export default function MapPage() {
  const [corridors, setCorridors] = useState([])
  const load = useCallback(async () => setCorridors(await Dashboard.map()), [])
  useEffect(() => { load() }, [load])

  return (
    <>
      <Header title="Corridor Maintenance Map" subtitle="Live maintenance status across railway corridors" onRefresh={load} />
      <div className="p-6 grid grid-cols-1 xl:grid-cols-4 gap-6">
        <div className="xl:col-span-3 bg-white rounded-xl border border-slate-200 shadow-sm p-2" style={{ height: '32rem' }}>
          <MapContainer center={[22.5, 79]} zoom={5} scrollWheelZoom>
            <TileLayer
              attribution='&copy; OpenStreetMap contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {corridors.map((c) => {
              const pts = corridorLatLngs(c.stations)
              const color = STATUS_COLOR[c.status] || '#3b82f6'
              return (
                <div key={c.corridor_id}>
                  {pts.length > 1 && (
                    <Polyline positions={pts} pathOptions={{ color, weight: 5, opacity: 0.8 }}>
                      <LTooltip sticky>
                        <b>{c.name}</b><br />
                        {c.pending} pending · {c.critical} critical · {c.planned_blocks} blocks
                      </LTooltip>
                    </Polyline>
                  )}
                  {c.stations.map((s) => STATION_COORDS[s.code] && (
                    <CircleMarker key={s.code} center={STATION_COORDS[s.code]} radius={4}
                      pathOptions={{ color, fillColor: color, fillOpacity: 1 }}>
                      <LTooltip>{s.name} ({s.code})</LTooltip>
                    </CircleMarker>
                  ))}
                </div>
              )
            })}
          </MapContainer>
        </div>

        <div className="space-y-3">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-3">
            <h3 className="font-bold text-slate-700 text-sm mb-2">Legend</h3>
            {[['critical', 'Critical defects present'], ['attention', 'High pending load'], ['normal', 'Normal']].map(([k, l]) => (
              <div key={k} className="flex items-center gap-2 text-xs text-slate-600 py-0.5">
                <span className="w-4 h-1.5 rounded" style={{ background: STATUS_COLOR[k] }} /> {l}
              </div>
            ))}
          </div>
          <div className="space-y-2 max-h-96 overflow-y-auto scrollbar-thin">
            {corridors.map((c) => (
              <div key={c.corridor_id} className="bg-white rounded-xl border border-slate-200 shadow-sm p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-700 text-sm truncate" title={c.name}>{c.name}</span>
                  <span className="w-3 h-3 rounded-full shrink-0" style={{ background: STATUS_COLOR[c.status] }} />
                </div>
                <div className="text-[11px] text-slate-400">{c.corridor_id.replace('COR-', '')} · {c.traffic_gmt} GMT</div>
                <div className="mt-1 grid grid-cols-3 gap-1 text-center text-xs">
                  <Mini v={c.pending} l="pending" />
                  <Mini v={c.critical} l="critical" color="text-red-600" />
                  <Mini v={c.planned_blocks} l="blocks" color="text-blue-600" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}

function Mini({ v, l, color = 'text-slate-700' }) {
  return (
    <div className="bg-slate-50 rounded p-1">
      <div className={`font-bold ${color}`}>{v}</div>
      <div className="text-slate-400 text-[10px]">{l}</div>
    </div>
  )
}
