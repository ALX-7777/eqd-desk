/**
 * Small reusable control primitives for the exotics views: a labelled slider with
 * a live value readout, and a segmented button group.
 */

interface LabeledSliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  display: string
  onChange: (v: number) => void
}

export function LabeledSlider({ label, value, min, max, step, display, onChange }: LabeledSliderProps) {
  return (
    <div className="field compact">
      <div className="field-head">
        <span className="field-label">{label}</span>
        <span className="field-display mono">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => {
          const v = Number(e.target.value)
          if (Number.isFinite(v)) onChange(v)
        }}
        aria-label={label}
      />
    </div>
  )
}

interface SegmentedProps<T extends string> {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  ariaLabel?: string
}

export function Segmented<T extends string>({ options, value, onChange, ariaLabel }: SegmentedProps<T>) {
  return (
    <div className="seg small" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.value}
          className={`seg-btn ${value === o.value ? 'active' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
