import type { DataFrame } from '../api/types'
import { reduceValues, seriesValues } from './reduce'

describe('reduceValues', () => {
  const values = [1, null, 3, 2]
  it.each([
    ['last', 2],
    ['mean', 2],
    ['max', 3],
    ['min', 1],
    ['sum', 6],
  ] as const)('%s', (how, expected) => {
    expect(reduceValues(values, how)).toBe(expected)
  })
  it('is null without numbers', () => {
    expect(reduceValues([null, null], 'last')).toBeNull()
  })
})

describe('seriesValues', () => {
  it('reduces wide frames per numeric field', () => {
    const wide: DataFrame = {
      refId: 'A',
      fields: [
        { name: 'time', type: 'time', values: [1, 2] },
        { name: 'a', type: 'number', labels: { cpu: '0' }, values: [1, 5] },
        { name: 'b', type: 'number', labels: { cpu: '1' }, values: [2, null] },
      ],
    }
    const out = seriesValues([wide], 'max')
    expect(out.map((s) => [s.name, s.value])).toEqual([
      ['a', 5],
      ['b', 2],
    ])
    expect(out[0].points).toEqual([
      [1, 1],
      [2, 5],
    ])
  })

  it('turns table-shaped frames into one series per row', () => {
    const table: DataFrame = {
      refId: 'A',
      fields: [
        { name: 'time', type: 'time', values: [9, 9] },
        { name: '__name__', type: 'string', values: ['up', 'up'] },
        { name: 'job', type: 'string', values: ['node', 'prom'] },
        { name: 'value', type: 'number', values: [1, 0] },
      ],
    }
    const out = seriesValues([table], 'last')
    expect(out.map((s) => [s.name, s.value])).toEqual([
      ['job=node', 1],
      ['job=prom', 0],
    ])
    expect(out[0].labels).toEqual({ __name__: 'up', job: 'node' })
  })
})
