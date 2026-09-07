// Approximate geo-coordinates for the demo station codes, so the Leaflet map
// can plot corridors as polylines with maintenance-status colouring.
export const STATION_COORDS = {
  NDLS: [28.6428, 77.2191], GZB: [28.6675, 77.4388], ALJN: [27.8974, 78.088],
  TDL: [27.2166, 78.2386], ETW: [26.7855, 79.015], CNB: [26.4499, 80.3319],
  FTP: [25.93, 80.81], ALD: [25.4519, 81.826], MZP: [25.146, 82.569],
  DDU: [25.2815, 83.1216], BRC: [22.3072, 73.1812], BH: [21.7051, 72.9959],
  ANND: [22.5645, 72.9289], ST: [21.1959, 72.8302], HWH: [22.5839, 88.3425],
  BWN: [23.2324, 87.8615], DGR: [23.5204, 87.3119], ASN: [23.6739, 86.9524],
  SBC: [12.9784, 77.5726], BNC: [12.9985, 77.6015], BWT: [12.9917, 78.1748],
  KPN: [12.7409, 78.3428], JTJ: [12.5697, 78.5747], BSL: [21.0447, 75.7851],
  AK: [20.7096, 77.0026], BD: [20.8656, 77.7398], WR: [20.7453, 78.6022],
  NGP: [21.1535, 79.0882],
}

export const STATUS_COLOR = {
  critical: '#dc2626',
  attention: '#ea580c',
  normal: '#16a34a',
}

export function corridorLatLngs(stations) {
  return stations
    .map((s) => STATION_COORDS[s.code])
    .filter(Boolean)
}
