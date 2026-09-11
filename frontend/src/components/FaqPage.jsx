import { useEffect, useState } from 'react'
import { marked } from 'marked'
import { getFaq } from '../api'

// Standalone page (frontend/faq.html), opened in a new tab from the menu's
// Help submenu - not a Popup like Settings/Help/About, since FAQ content is
// meant to be its own bookmarkable/shareable page. Content comes from the
// faq_entries table, one row per question - question/answer are Markdown,
// rendered here rather than trusting/injecting raw stored HTML.
export default function FaqPage() {
  const [entries, setEntries] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    getFaq()
      .then((result) => {
        if (!cancelled) setEntries(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="faq-page">
      <h1>Frequently Asked Questions</h1>
      {error && <p className="login-error">{error}</p>}
      {!error && entries === null && <p>Loading…</p>}
      {entries !== null && entries.length === 0 && <p>No FAQ entries yet.</p>}
      {entries !== null &&
        entries.map((entry) => (
          <section key={entry.id} className="faq-entry">
            <h2 dangerouslySetInnerHTML={{ __html: marked.parseInline(entry.question) }} />
            <div dangerouslySetInnerHTML={{ __html: marked.parse(entry.answer) }} />
          </section>
        ))}
    </div>
  )
}
