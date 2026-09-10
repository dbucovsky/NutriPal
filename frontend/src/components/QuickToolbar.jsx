// Shared quick-collapse toolbar (expand all / collapse all / collapse-to-
// level / reset) - identical across Food, Heart Rate, and Sleep, which only
// differ in which levels they offer (Food adds a meal leaf; Heart Rate and
// Sleep stop at day). `levels` is that page's own ordered (coarsest-first)
// list of { level, badge, title }. A collapse-to-level button disables
// itself when the current view has no node of that level (e.g. Y/Q/M gray
// out on a Week view).
export default function QuickToolbar({ levels, availableLevels, onExpandAll, onCollapseAll, onCollapseTo, onReset }) {
  return (
    <div className="quick-toolbar">
      <button type="button" className="toolbar-badge" title="Expand all" onClick={onExpandAll}>
        ⤓
      </button>
      <button type="button" className="toolbar-badge" title="Collapse all" onClick={onCollapseAll}>
        ⤒
      </button>
      <span className="toolbar-sep" />
      {levels.map(({ level, badge, title }) => (
        <button
          key={level}
          type="button"
          className="toolbar-badge"
          title={title}
          disabled={!availableLevels.has(level)}
          onClick={() => onCollapseTo(level)}
        >
          {badge}
        </button>
      ))}
      <span className="toolbar-sep" />
      <button type="button" className="toolbar-badge" title="Reset to default" onClick={onReset}>
        ↻
      </button>
    </div>
  )
}
