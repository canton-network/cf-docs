/**
 * Convert a slice of splice RST (from .. include:: targets) into embeddable MDX.
 * Used with export config options.transform === "rstinclude".
 */

function trimBlankEdges(content) {
    return content.replace(/^\s*\n+/, '').replace(/\n+\s*$/, '')
}

function stripLeadingRstComments(lines) {
    let i = 0
    while (i < lines.length) {
        const t = lines[i].trim()
        if (t === '') {
            i++
            continue
        }
        if (/^\.\./.test(t) && !/^\.\.\s+[\w-]+::/.test(t)) {
            i++
            continue
        }
        if (/^Copyright\b/i.test(t) || /^SPDX-License-Identifier:/i.test(t)) {
            i++
            continue
        }
        break
    }
    return lines.slice(i)
}

function dedentBlock(lines) {
    if (lines.length === 0) return []
    const indents = lines
        .filter((l) => l.trim() !== '')
        .map((l) => (l.match(/^(\s*)/) || ['', ''])[1].length)
    const min = indents.length ? Math.min(...indents) : 0
    return lines.map((l) => (l.trim() === '' ? '' : l.slice(min)))
}

function inlineRstMarkup(text, refTargets = {}) {
    let out = text
    out = out.replace(
        /:ref:`([^<]+?)\s*<([^>]+)>`/g,
        (_, label, target) => {
            const href = refTargets[target.trim()]
            return href ? `[${label.trim()}](${href})` : label.trim()
        }
    )
    out = out.replace(/:ref:`([^`]+)`/g, (_, target) => {
        const key = target.trim()
        const href = refTargets[key]
        if (href) {
            const label = key.replace(/_/g, ' ')
            return `[${label}](${href})`
        }
        return key
    })
    out = out.replace(/\*\*([^*]+)\*\*/g, '**$1**')
    out = out.replace(/``([^`]+)``/g, '`$1`')
    return out
}

function fieldListToMarkdown(lines, startIdx, refTargets = {}) {
    const items = []
    let i = startIdx
    while (i < lines.length) {
        const line = lines[i]
        const lt = line.trim()
        if (lt === '') {
            i++
            continue
        }
        if (/^\.\.\s+[\w-]+::/.test(lt)) break
        if (/^\s/.test(line)) break
        if (!/^[A-Z][A-Z0-9_]+$/.test(lt)) break
        const term = lt
        i++
        const body = []
        while (i < lines.length && /^\s+/.test(lines[i])) {
            const bt = lines[i].trim()
            if (bt === '') {
                i++
                continue
            }
            if (/^\.\.\s+/.test(bt)) break
            body.push(bt)
            i++
        }
        const bodyText = inlineRstMarkup(body.join(' '), refTargets)
        const linkified = bodyText
            .replace(
                /form \|generic_sv_url\|/g,
                'form <a href="|generic_sv_url|">|generic_sv_url|</a>'
            )
            .replace(
                /use \|gsf_sv_url\|/g,
                'use <a href="|gsf_sv_url|">|gsf_sv_url|</a>'
            )
        if (term === 'ONBOARDING_SECRET') {
            items.push({
                type: 'paragraph',
                text: `**${term}**\n${linkified}`,
            })
        } else {
            items.push({
                type: 'bullet',
                text: `**${term}** — ${linkified}`,
            })
        }
    }
    return { next: i, items }
}

function readDirectiveBlock(lines, startIdx) {
    const body = []
    let i = startIdx
    while (i < lines.length) {
        const line = lines[i]
        if (line.trim() === '') {
            body.push('')
            i++
            continue
        }
        if (!/^\s/.test(line) && /^\.\.\s+/.test(line)) break
        if (!/^\s/.test(line) && line.trim() !== '' && body.length > 0) break
        body.push(line)
        i++
    }
    return { body: dedentBlock(body), next: i }
}

function convertRstIncludeToMdx(content, options = {}) {
    const refTargets = options.refTargets || {}
    const rawLines = trimBlankEdges(content).split('\n')
    const lines = stripLeadingRstComments(rawLines)
    const out = []
    let i = 0

    while (i < lines.length) {
        const line = lines[i]
        const trimmed = line.trim()

        if (trimmed === '') {
            i++
            continue
        }

        const warning = trimmed.match(/^\.\.\s+warning::\s*$/)
        if (warning) {
            const block = readDirectiveBlock(lines, i + 1)
            const inner = block.body
                .filter((l) => l.trim() !== '')
                .map((l) => inlineRstMarkup(l.trim(), refTargets))
                .join('\n\n')
            out.push(`<Warning>\n\n${inner}\n\n</Warning>`)
            i = block.next
            continue
        }

        const note = trimmed.match(/^\.\.\s+note::\s*$/)
        if (note) {
            const block = readDirectiveBlock(lines, i + 1)
            const inner = block.body
                .filter((l) => l.trim() !== '')
                .map((l) => inlineRstMarkup(l.trim(), refTargets))
                .join('\n\n')
            out.push(`<Note>\n\n${inner}\n\n</Note>`)
            i = block.next
            continue
        }

        const admonition = trimmed.match(/^\.\.\s+admonition::\s*(.+)\s*$/)
        if (admonition) {
            const title = admonition[1].trim()
            const block = readDirectiveBlock(lines, i + 1)
            const parts = []
            let j = 0
            const bodyLines = block.body
            while (j < bodyLines.length) {
                const bl = bodyLines[j].trim()
                if (bl === '') {
                    j++
                    continue
                }
                if (/^\.\.\s+parsed-literal::\s*$/.test(bl)) {
                    j++
                    const codeBlock = readDirectiveBlock(bodyLines, j)
                    const code = codeBlock.body
                        .filter((l) => l.trim() !== '')
                        .join('\n')
                    parts.push('```bash\n' + code + '\n```')
                    j = codeBlock.next
                    continue
                }
                const para = []
                while (j < bodyLines.length && bodyLines[j].trim() !== '') {
                    if (/^\.\.\s+/.test(bodyLines[j].trim())) break
                    para.push(bodyLines[j].trim())
                    j++
                }
                if (para.length) {
                    parts.push(inlineRstMarkup(para.join(' '), refTargets))
                }
            }
            const wrapper =
                title.toLowerCase().includes('devnet') ||
                title.toLowerCase().includes('devnet-only')
                    ? '<div data-network-only="devnet">\n\n'
                    : ''
            const wrapperEnd = wrapper ? '\n\n</div>' : ''
            const inner = parts
                .map((p) =>
                    p.startsWith('```') ? p : `<Note>\n\n${p}\n\n</Note>`
                )
                .join('\n\n')
            out.push(`${wrapper}${inner}${wrapperEnd}`)
            i = block.next
            continue
        }

        const parsedLiteral = trimmed.match(/^\.\.\s+parsed-literal::\s*$/)
        if (parsedLiteral) {
            const block = readDirectiveBlock(lines, i + 1)
            const code = block.body
                .filter((l) => l.trim() !== '')
                .join('\n')
            out.push('```bash\n' + code + '\n```')
            i = block.next
            continue
        }

        const codeBlock = trimmed.match(/^\.\.\s+code(?:-block)?::\s*(\S*)\s*$/)
        if (codeBlock) {
            const lang = codeBlock[1] || 'bash'
            const block = readDirectiveBlock(lines, i + 1)
            const code = block.body
                .filter((l) => l.trim() !== '')
                .join('\n')
            out.push('```' + lang + '\n' + code + '\n```')
            i = block.next
            continue
        }

        if (/^\.\.\s+/.test(trimmed)) {
            i++
            continue
        }

        if (!/^\s/.test(line) && /^[A-Z][A-Z0-9_]+$/.test(trimmed)) {
            const fl = fieldListToMarkdown(lines, i, refTargets)
            let inList = false
            for (const item of fl.items) {
                if (item.type === 'bullet') {
                    if (!inList) {
                        out.push('<ul>')
                        inList = true
                    }
                    out.push(`<li>${item.text}</li>`)
                } else {
                    if (inList) {
                        out.push('</ul>')
                        inList = false
                    }
                    out.push(`<p>${item.text.replace(/\n/g, '<br />\n')}</p>`)
                }
            }
            if (inList) out.push('</ul>')
            i = fl.next
            continue
        }

        if (trimmed.startsWith('- ')) {
            const items = []
            while (i < lines.length) {
                const t = lines[i].trim()
                if (t.startsWith('- ')) {
                    items.push(
                        inlineRstMarkup(t.replace(/^-\s+/, ''), refTargets)
                    )
                    i++
                } else if (t === '') {
                    i++
                    if (
                        i >= lines.length ||
                        (!lines[i].trim().startsWith('- ') &&
                            !/^\s+/.test(lines[i]))
                    ) {
                        break
                    }
                } else if (/^\s/.test(lines[i]) && items.length > 0) {
                    items[items.length - 1] +=
                        ' ' + inlineRstMarkup(t, refTargets)
                    i++
                } else {
                    break
                }
            }
            out.push('<ul>')
            for (const item of items) {
                out.push(`<li>${item}</li>`)
            }
            out.push('</ul>')
            continue
        }

        if (!/^\s/.test(line)) {
            const para = []
            while (i < lines.length) {
                const pl = lines[i]
                const pt = pl.trim()
                if (pt === '') break
                if (/^\.\.\s+/.test(pt)) break
                if (pt.startsWith('- ')) break
                if (!/^\s/.test(pl) && /^[A-Z][A-Z0-9_]+$/.test(pt)) {
                    break
                }
                para.push(pt)
                i++
            }
            if (para.length) {
                out.push(
                    `<p>${inlineRstMarkup(para.join(' '), refTargets)}</p>`
                )
            }
            continue
        }

        i++
    }

    return trimBlankEdges(out.join('\n\n'))
}

module.exports = {
    convertRstIncludeToMdx,
    stripLeadingRstComments,
}
