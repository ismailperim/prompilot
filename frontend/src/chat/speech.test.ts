import { guessLang, stripMarkdown } from './speech'

describe('speech helpers', () => {
  it('strips the markdown the chat renders', () => {
    expect(stripMarkdown('Added **RAM (15 dk)** using `node_memory_MemTotal_bytes`.')).toBe(
      'Added RAM (15 dk) using node_memory_MemTotal_bytes.',
    )
  })

  it('guesses Turkish and English', () => {
    expect(guessLang('son 15 dakikalık RAM tüketimini göster')).toBe('tr-TR')
    expect(guessLang('show the last 15 minutes of memory')).toBe('en-US')
    expect(guessLang('node_load1', 'de-DE')).toBe('de-DE')
  })
})
