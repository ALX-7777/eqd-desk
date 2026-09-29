import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import App from '../../App'

describe('App (Greeks Lab) smoke test', () => {
  it('renders the shell, market strip, price and greeks without crashing', () => {
    render(<App />)
    expect(screen.getByText('EQD Desk')).toBeInTheDocument()
    expect(screen.getByText('Price & Greeks')).toBeInTheDocument()
    // every greek label shows up at least once (readout or chips)
    for (const label of ['Delta', 'Gamma', 'Vega', 'Theta', 'Vanna', 'Volga', 'Charm', 'Color']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    // the seed badge is visible
    expect(screen.getByText(/STATIC SEED/)).toBeInTheDocument()
  })

  it('selecting a greek updates the education card', () => {
    render(<App />)
    // education card defaults to Delta
    const eduCard = document.querySelector('.edu-card') as HTMLElement
    expect(within(eduCard).getByText('Delta (Δ)')).toBeInTheDocument()
    // click the Gamma chip
    const chips = document.querySelectorAll('.chip')
    const gammaChip = Array.from(chips).find((c) => c.textContent === 'Gamma') as HTMLElement
    fireEvent.click(gammaChip)
    expect(within(eduCard).getByText('Gamma (Γ)')).toBeInTheDocument()
  })

  it('toggling call/put changes the readout tag', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'PUT' }))
    // the readout tag should now read PUT (appears in the title row)
    expect(screen.getAllByText('PUT').length).toBeGreaterThan(0)
  })

  it('switches to the Strategy Builder and applies a preset', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Strategy Builder' }))
    // structure / legs / net position panels render
    expect(screen.getByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Legs' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Net Position' })).toBeInTheDocument()
    // a net premium tag (debit or credit) is shown
    expect(screen.getByText(/DEBIT|CREDIT/)).toBeInTheDocument()
    // switching preset doesn't crash and updates the structure
    fireEvent.click(screen.getByRole('button', { name: 'Iron condor' }))
    expect(screen.getByText(/DEBIT|CREDIT/)).toBeInTheDocument()
    // the legs table has rows (4 for an iron condor)
    expect(document.querySelectorAll('.leg-row').length).toBe(4)
  })

  it('switches to Exotics and between sub-instruments', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Exotics' }))
    // default sub-view is the barrier
    expect(screen.getByRole('heading', { name: 'Barrier' })).toBeInTheDocument()
    // switch to the variance swap
    fireEvent.click(screen.getByRole('button', { name: 'Variance swap' }))
    expect(screen.getByRole('heading', { name: 'Fair variance' })).toBeInTheDocument()
    // and to the digital
    fireEvent.click(screen.getByRole('button', { name: 'Digital' }))
    expect(screen.getByRole('heading', { name: 'Digital' })).toBeInTheDocument()
  })

  it('runs the trading simulator loop: RFQ queue → quote → tick', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Simulator' }))
    expect(screen.getByRole('heading', { name: 'Client RFQs' })).toBeInTheDocument()
    // request an RFQ into the queue and quote it
    fireEvent.click(screen.getByRole('button', { name: /Request a quote/ }))
    expect(screen.getByRole('button', { name: 'Quote' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Quote' }))
    // advance the clock; the P&L explain still renders (no crash)
    fireEvent.click(screen.getByRole('button', { name: /Tick/ }))
    expect(screen.getByRole('heading', { name: 'P&L explain (cumulative)' })).toBeInTheDocument()
  })

  it('switches the simulator to historical replay mode', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Simulator' }))
    fireEvent.click(screen.getByRole('button', { name: 'Replay' }))
    expect(screen.getByText(/Undisclosed slice/)).toBeInTheDocument()
  })
})
