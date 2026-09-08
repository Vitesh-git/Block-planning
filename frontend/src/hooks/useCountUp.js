import { useEffect, useRef, useState } from 'react'

// Smoothly animates a number from 0 to `target` (ease-out cubic).
export function useCountUp(target, duration = 950) {
  const [val, setVal] = useState(0)
  const raf = useRef()
  useEffect(() => {
    const t = Number(target) || 0
    let start
    cancelAnimationFrame(raf.current)
    const step = (ts) => {
      if (start === undefined) start = ts
      const p = Math.min(1, (ts - start) / duration)
      setVal(t * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf.current = requestAnimationFrame(step)
      else setVal(t)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [target, duration])
  return val
}
