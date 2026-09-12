import type { MerchantExchange } from '../types'

interface Props {
  header: string
  bondlayerEnabled: boolean
  exchanges: MerchantExchange[]
}

/** The switch, shown as what it actually is: one token in one request header,
 *  and the merchant pruning the extension because it was not declared. */
export default function UCPLog({ header, bondlayerEnabled, exchanges }: Props) {
  return (
    <section className="ucp-log">
      <h3>UCP negotiation</h3>

      <div className={`ucp-header ${bondlayerEnabled ? 'on' : 'off'}`}>
        <span className="ucp-header-label">
          UCP-Agent {bondlayerEnabled ? '(BondLayer declared)' : '(BondLayer not declared)'}
        </span>
        <code>{header}</code>
      </div>

      <table className="ucp-table">
        <thead>
          <tr>
            <th>Merchant</th>
            <th>Status</th>
            <th>Active</th>
            <th>Pruned</th>
            <th>Extension</th>
            <th>Products</th>
            <th>Records</th>
          </tr>
        </thead>
        <tbody>
          {exchanges.map((ex) => (
            <tr key={ex.merchant} className={ex.error ? 'exchange-error' : ''}>
              <td>{ex.merchant}</td>
              <td>{ex.status_code || 'failed'}</td>
              <td>{Object.keys(ex.active_capabilities).length}</td>
              <td>{Object.keys(ex.pruned_capabilities).length}</td>
              <td>{ex.extension_served ? 'served' : 'pruned'}</td>
              <td>{ex.product_count}</td>
              <td>{ex.record_count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="ucp-note">
        Same route, same response builder, same fan-out. The only difference between
        the two runs is whether the agent declared org.bondlayer.benefit_value.
      </p>
    </section>
  )
}
