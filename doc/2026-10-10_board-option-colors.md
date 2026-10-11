# Board option colors

The colors and descriptions of every option of the board's single-select fields and of the Area labels, as chosen by
the owner on 2026-10-10 and applied by the ticket that references this file. This is the absolute list, not only what
changed. The description is the official one from *Appendix C: Ticket fields reference* of the governance standard
(for Size, the estimated effort; for Ticket type, the Type table). The Attention colors are the standard's own.

The colors GitHub offers for a board option are GRAY, BLUE, GREEN, YELLOW, ORANGE, RED, PINK and PURPLE. A label takes a
six-digit hex color instead.

## Status

| Option | Description | Color |
| ------ | ----------- | ----- |
| ToDo | Accepted, not scheduled. | GREEN |
| OnDeck | Chosen to be worked on next. | BLUE |
| InProgress | Work has started. | YELLOW |
| Review | The developer (or an assistant) believes the work is done and wants it checked. May be a real review or a formality. | ORANGE |
| Completed | A human has verified the result. | PURPLE |
| Suspended | Set aside, expected to resume. | PINK |
| Abandoned | Dropped, not expected to return. | RED |

## Ticket type

| Option | Description | Color |
| ------ | ----------- | ----- |
| Feature | New capability that did not exist before. | PURPLE |
| Enhancement | An improvement to something that already works: better performance, smarter behavior, easier use. | GREEN |
| Change | A change to existing behavior that is neither an improvement nor a fix: a new default, a different threshold, an adjustment someone asked for. | BLUE |
| Bug | Something that behaves differently from what was intended, and the fix for it. | PINK |
| Refactor | Internal restructuring with no change in what the product does. | ORANGE |
| Task | Work that does not change the product's behavior: testing, analyzing, building, releasing, writing documentation, and creating a new tool. | YELLOW |
| Version | Bookkeeping ticket for one version. It does no work and never counts toward a bump. | GRAY |
| Alert | An automatic check that needs a person to review something, such as a detected bypass or a stale planned version. It never counts toward a bump. | RED |

## Origin

| Option | Description | Color |
| ------ | ----------- | ----- |
| Backfilled | Created after the work was done, to replace a ticket-less placeholder in the changelog. | YELLOW |
| Backdated | Created to document history from before the process existed. | ORANGE |

## Waiting

| Option | Description | Color |
| ------ | ----------- | ----- |
| Needs input | The ticket is waiting for someone's feedback, an answer to a question, or a verification. | ORANGE |

## Attention (unchanged)

| Option | Description | Color |
| ------ | ----------- | ----- |
| Fine | Looked at: nothing is wrong, or it was put right. | GREEN |
| Acknowledged | Looked at: something has to be done, and it is handled elsewhere (another ticket, or this ticket moved back to ToDo, OnDeck, InProgress or Suspended). A reply says where. | PURPLE |
| Watch | An open flag, the lowest level. | YELLOW |
| Caution | An open flag, the middle level. | ORANGE |
| AtRisk | An open flag, the highest level. Reserved: no rule uses it yet. | RED |

## Resolution

| Option | Description | Color |
| ------ | ----------- | ----- |
| Done | The work was done and verified. | GREEN |
| Duplicate | The same as another ticket, which the comment links. | GRAY |
| Invalid | Not a real problem, or based on a misunderstanding; includes a fault that cannot be reproduced. | PINK |
| WontFix | A valid request or fault that was decided not to act on. | ORANGE |
| Superseded | Replaced by a different approach or ticket: the work was real, but something else took its place. | BLUE |
| Obsolete | No longer relevant because the thing it was about changed or was removed. | PURPLE |

## Delivery

| Option | Description | Color |
| ------ | ----------- | ----- |
| Committed | Optional personal marker: the work is committed locally and not yet pushed. | BLUE |
| Pushed | Code for the ticket is on a branch on the hosting service, not yet merged. | GREEN |
| Merged | The work is on main, in a finalized version. | PURPLE |
| Implemented | The work is in effect and involved no file change (a setting, a secret, a check that was run). | GREEN |
| Released | The version containing it has been declared a release. | RED |
| Dropped | The code or version was planned or pushed but will never be delivered. | GRAY |

## Priority

| Option | Description | Color |
| ------ | ----------- | ----- |
| Critical | Act now: a fault in released software, or an unverified bypass. Every Alert ticket is Critical. | RED |
| Urgent | Must be in the current or next version; it blocks other work or a release. | ORANGE |
| High | Important; planned for the next few versions. | YELLOW |
| Normal | The default for ordinary work. | BLUE |
| Low | Nice to have; do it when convenient. | GREEN |
| Wishlist | An idea or backlog item with no commitment to do it. | GRAY |

## Size

| Option | Description | Color |
| ------ | ----------- | ----- |
| XS | Estimated effort: up to 1 hour. | GREEN |
| S | Estimated effort: up to 4 hours. | BLUE |
| M | Estimated effort: up to 2 days. | YELLOW |
| L | Estimated effort: up to 2 weeks. | ORANGE |
| XL | Estimated effort: more than 2 weeks. | RED |

## Risk

| Option | Description | Color |
| ------ | ----------- | ----- |
| 1 Very low | Nothing depends on it. | GREEN |
| 2 Low | Isolated and easy to undo. | BLUE |
| 3 Medium | Some uncertainty. | YELLOW |
| 4 High | Likely to go wrong: critical failure or major delay. | ORANGE |
| 5 Very high | May not be feasible. | RED |

## Labels (Area)

| Label | Description | Color name | Hex |
| ----- | ----------- | ---------- | --- |
| requirements | Working out what is needed, with the people who need it. | Blue | 2196F3 |
| research | Investigating options or unknowns: technologies, parts, approaches. | Purple | 8E24AA |
| design | Deciding how it will be built, before building it (software, hardware, mechanical). | Teal | 00ACC1 |
| implementation | Producing the thing itself: code, circuit, enclosure, configuration of the product. | Dark Blue | 1565C0 |
| assembly | Putting physical parts together: electronics, mechanical parts, enclosures. | Brown | 8D6E63 |
| testing | Unit, functional and acceptance or QA testing. | Green | 43A047 |
| analysis | Examining existing behaviour or data to understand it, without necessarily fixing it. | Indigo | 5E35B1 |
| debugging | Finding and fixing the cause of a fault. | Red | E53935 |
| documentation | Wiki, readme, guides, comments and other written documentation. | Gold | C0A000 |
| tool | Developer tooling and scripts that support the work. | Slate | 546E7A |
| process | How the team works: git, changelog, versioning, hooks, the board, repository settings. | Dark Gray | 424242 |
| config | Settings that tune how the product behaves: feature flags, pin assignments, intervals. | Amber | FB8C00 |
| content | Data the product or its tests use: test fixtures, sample data, lookup tables, a database seed. | Pink | D81B60 |
| build | Build system, toolchain, compiling and releasing. | Orange | EF6C00 |
| dummy | A throwaway ticket or version made to test the automation; left out of the board's working views. | Light Gray | BDBDBD |
