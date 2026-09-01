import Num from '../anim/Num'
import { useTilt } from '../anim/hooks'
import { fmt } from '../data'

export default function StatCard({ label, value, unit, hint }) {
  const card = useTilt({ max: 5.5, lift: 5 })
  /* 31,000 reads as "31k" — but it still has to count through the real
     number, otherwise the tile lands on its value in three visible steps */
  const format = unit === 'k' ? (n) => `${Math.round(n / 1000)}k` : fmt

  return (
    <div className="card stat" ref={card}>
      <div className="stat__head">
        <span className="card-label">{label}</span>
        <span className="badge-24h">24h</span>
      </div>
      <Num className="stat__value" value={value} from={0} format={format} delay={0.1} flash={false} tag="div" />
      <div className="stat__hint">
        <b>{hint[0]}</b> {hint[1]}
      </div>
    </div>
  )
}
