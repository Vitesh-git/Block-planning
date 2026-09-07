// Central Chart.js registration so every chart component shares one setup.
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
)

export const PRIORITY_PALETTE = {
  Critical: '#dc2626',
  High: '#ea580c',
  Medium: '#ca8a04',
  Low: '#16a34a',
}

export const baseOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { labels: { boxWidth: 12, font: { size: 11 } } },
  },
}
