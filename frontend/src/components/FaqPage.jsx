import { useEffect, useState } from 'react'
import { marked } from 'marked'
import { getFaq } from '../api'

// Standalone page (frontend/faq.html), opened in a new tab from the menu's
// Help submenu - not a Popup like Settings/Help/About, since FAQ content is
// meant to be its own bookmarkable/shareable page. Content comes from the
// faq_entries table, grouped by lut_faq_section (General/overview first,
// then one section per tab in the same order the tab bar itself uses, then
// Settings, then Contact & Support last - see faq.php, which already
// returns entries pre-sorted by section then display_order). question/
// answer are Markdown, rendered here rather than trusting/injecting raw
// stored HTML. Each answer collapses behind its question by default (a
// <details>, the same collapsible convention used throughout the rest of
// the app) rather than every answer being shown open at once.
function groupBySection(entries) {
  const sections = []
  let current = null
  for (const entry of entries) {
    if (!current || current.sectionId !== entry.section_id) {
      current = { sectionId: entry.section_id, sectionName: entry.section, entries: [] }
      sections.push(current)
    }
    current.entries.push(entry)
  }
  return sections
}

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

  const sections = entries ? groupBySection(entries) : []

  return (
    <div className="faq-page">
      <h1>Frequently Asked Questions</h1>
      {error && <p className="login-error">{error}</p>}
      {!error && entries === null && <p>Loading…</p>}
      {entries !== null && entries.length === 0 && <p>No FAQ entries yet.</p>}
      {sections.map((section) => (
        <section key={section.sectionId} className="faq-section">
          <h2>{section.sectionName}</h2>
          {section.entries.map((entry) => (
            <details key={entry.id} className="faq-entry">
              <summary className="faq-question" dangerouslySetInnerHTML={{ __html: marked.parseInline(entry.question) }} />
              <div className="faq-answer" dangerouslySetInnerHTML={{ __html: marked.parse(entry.answer) }} />
            </details>
          ))}
        </section>
      ))}
    </div>
  )
}
