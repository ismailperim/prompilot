import type { DataFrame } from '../api/types'
import { frameToTabular, toCsv } from './tabular'

describe('frameToTabular', () => {
  it('turns a wide frame into a row per timestamp', () => {
    const wide: DataFrame = {
      refId: 'A',
      fields: [
        { name: 'time', type: 'time', values: [0, 60000] },
        { name: 'cpu 0', type: 'number', values: [0.1, null] },
        { name: 'cpu 1', type: 'number', values: [0.5, 0.6] },
      ],
    }
    expect(frameToTabular(wide)).toEqual({
      columns: ['time', 'cpu 0', 'cpu 1'],
      rows: [
        ['1970-01-01T00:00:00.000Z', 0.1, 0.5],
        ['1970-01-01T00:01:00.000Z', null, 0.6],
      ],
    })
  })

  it('keeps table-shaped frames as rows with label columns first', () => {
    const table: DataFrame = {
      refId: 'A',
      fields: [
        { name: 'time', type: 'time', values: [0, 0] },
        { name: 'job', type: 'string', values: ['node', 'prom'] },
        { name: 'value', type: 'number', values: [1, 0] },
      ],
    }
    expect(frameToTabular(table).columns).toEqual(['time', 'job', 'value'])
    expect(frameToTabular(table).rows[1]).toEqual(['1970-01-01T00:00:00.000Z', 'prom', 0])
  })
})

describe('toCsv', () => {
  it('quotes what needs quoting', () => {
    expect(toCsv({ columns: ['a', 'b,c'], rows: [['x"y', null], [1, 2]] })).toBe('a,"b,c"\n"x""y",\n1,2')
  })
})
