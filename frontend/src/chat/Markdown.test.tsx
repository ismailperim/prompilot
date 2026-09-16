import { render, screen } from '@testing-library/react'
import { Markdown } from './Markdown'

describe('Markdown', () => {
  it('renders bold and inline code, keeps the rest as text', () => {
    render(<Markdown text={'Panel eklendi. **RAM (15 dk)** chart\'ı `node_memory_MemTotal_bytes` kullanıyor.'} />)
    expect(screen.getByText('RAM (15 dk)').tagName).toBe('STRONG')
    expect(screen.getByText('node_memory_MemTotal_bytes').tagName).toBe('CODE')
    expect(screen.getByText(/Panel eklendi\./)).toBeInTheDocument()
  })

  it('splits paragraphs on blank lines', () => {
    const { container } = render(<Markdown text={'one\n\ntwo'} />)
    expect(container.querySelectorAll('p')).toHaveLength(2)
  })
})
