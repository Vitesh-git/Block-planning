import { useEffect, useState } from 'react'
import { Corridors } from '../api/client'
import { corridorShort } from '../utils/domain'

// Fetches the corridor list once (module-cached) and returns a resolver that
// turns a corridor_id into its real name, e.g. "New Delhi – Kanpur (Grand Trunk)".
let _cache = null

export function useCorridorNames() {
  const [map, setMap] = useState(_cache || {})
  useEffect(() => {
    if (_cache) { setMap(_cache); return }
    Corridors.list()
      .then((list) => {
        const m = {}
        list.forEach((c) => { m[c.corridor_id] = c.name })
        _cache = m
        setMap(m)
      })
      .catch(() => {})
  }, [])
  return (id) => map[id] || corridorShort(id)
}
