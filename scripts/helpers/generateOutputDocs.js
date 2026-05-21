#!/usr/bin/env node

// generateOutputDocs.js
//
// - Reads a single export config: docs/config/exportConfig.json
// - Writes extracted snippets into: docs-output/<snippetName>.mdx
// - Resolves source files relative to the repo root
// - Adds a searchable source-snippet provenance comment to each output file

const fs = require('fs')
const path = require('path')
const { convertRstIncludeToMdx } = require('./rstIncludeToMdx')
const childProcess = require('child_process')

const REPO_ROOT = path.join(__dirname, '..', '..')
const EXPORT_CONFIG_PATH = path.join(__dirname, 'exportConfig.json')
const OUTPUT_FOLDER_PATH = path.join(REPO_ROOT, 'docs-output')

function runGit(args) {
    try {
        return childProcess
            .execFileSync('git', args, {
                cwd: REPO_ROOT,
                encoding: 'utf8',
                stdio: ['ignore', 'pipe', 'ignore'],
            })
            .trim()
    } catch (_) {
        return ''
    }
}

const SOURCE_COMMIT = runGit(['rev-parse', 'HEAD']) || 'unknown'

function getSourceRepoName() {
    if (process.env.SOURCE_REPO_NAME) {
        return process.env.SOURCE_REPO_NAME
    }

    const remoteUrl = runGit(['config', '--get', 'remote.origin.url'])
    const remoteMatch = remoteUrl.match(/([^/:]+?)(?:\.git)?$/)
    if (remoteMatch) {
        return remoteMatch[1]
    }

    return path.basename(REPO_ROOT)
}

const SOURCE_REPO_NAME = getSourceRepoName()

function readFileContent(filePath) {
    try {
        return fs.readFileSync(filePath, 'utf8')
    } catch (error) {
        throw new Error(`Failed to read file ${filePath}: ${error.message}`)
    }
}

function extractByLines(fileContent, start, end) {
    const lines = fileContent.split(/\r?\n/)
    const startLine = Number(start)
    const endLine = Number(end)

    if (
        startLine < 1 ||
        endLine < 1 ||
        startLine > lines.length ||
        endLine > lines.length
    ) {
        throw new Error(
            `Line numbers out of range: start=${startLine}, end=${endLine}, file has ${lines.length} lines`
        )
    }

    if (startLine > endLine) {
        throw new Error(
            `Invalid line range: start (${startLine}) must be <= end (${endLine})`
        )
    }

    return lines.slice(startLine - 1, endLine).join('\n')
}

function extractByStringMarker(fileContent, startMarker, endMarker) {
    const startIndex = fileContent.indexOf(startMarker)
    if (startIndex === -1) {
        throw new Error(`Start marker not found: "${startMarker}"`)
    }

    // Match Sphinx literalinclude :start-after: / :end-before: — exclude marker lines.
    let contentStart = fileContent.indexOf('\n', startIndex)
    if (contentStart === -1) {
        contentStart = startIndex + startMarker.length
    } else {
        contentStart += 1
    }

    const endIndex = fileContent.indexOf(endMarker, contentStart)
    if (endIndex === -1) {
        throw new Error(`End marker not found: "${endMarker}"`)
    }

    let contentEnd = fileContent.lastIndexOf('\n', endIndex)
    if (contentEnd < contentStart) {
        contentEnd = endIndex
    }

    return fileContent.substring(contentStart, contentEnd).trim()
}

function extractByRegexWrap(fileContent, startRegex, endRegex) {
    const startPattern = new RegExp(startRegex)
    const endPattern = new RegExp(endRegex)

    const startMatch = fileContent.match(startPattern)
    if (!startMatch) {
        throw new Error(`Start regex pattern not found: "${startRegex}"`)
    }

    const contentStart = startMatch.index + startMatch[0].length
    const remainingContent = fileContent.substring(contentStart)
    const endMatch = remainingContent.match(endPattern)

    if (!endMatch) {
        throw new Error(`End regex pattern not found: "${endRegex}"`)
    }

    return remainingContent.substring(0, endMatch.index).trim()
}

function extractByJsonIndex(fileContent, start, end) {
    let arr
    try {
        arr = JSON.parse(fileContent)
    } catch (e) {
        throw new Error(`File is not valid JSON: ${e.message}`)
    }
    if (!Array.isArray(arr)) {
        throw new Error(
            'JSON root must be an array for location type jsonIndex'
        )
    }
    const startIdx = Number(start)
    const endIdx = Number(end)
    if (
        startIdx < 0 ||
        endIdx < 0 ||
        startIdx >= arr.length ||
        endIdx >= arr.length
    ) {
        throw new Error(
            `Array index out of range: start=${startIdx}, end=${endIdx}, array length=${arr.length}`
        )
    }
    if (startIdx > endIdx) {
        throw new Error(
            `Invalid index range: start (${startIdx}) must be <= end (${endIdx})`
        )
    }
    if (startIdx === endIdx) {
        const item = arr[startIdx]
        return typeof item === 'string' ? item : String(item)
    }
    return arr
        .slice(startIdx, endIdx + 1)
        .map((item) => (typeof item === 'string' ? item : String(item)))
        .join('\n')
}

function extractSnippetContent(fileContent, location) {
    switch (location.type) {
        case 'fullFile':
            return fileContent

        case 'lines':
            return extractByLines(fileContent, location.start, location.end)

        case 'jsonIndex':
            return extractByJsonIndex(fileContent, location.start, location.end)

        case 'stringMarker':
            return extractByStringMarker(
                fileContent,
                location.start,
                location.end
            )

        case 'regexWrap':
            return extractByRegexWrap(fileContent, location.start, location.end)

        default:
            throw new Error(`Unknown location type: ${location.type}`)
    }
}

function normalizeIndent(content) {
    const lines = content.split('\n')

    let minIndent = null
    for (const line of lines) {
        if (line.trim() === '') continue
        const match = line.match(/^(\s*)/)
        const indent = match ? match[1].length : 0
        if (minIndent === null || indent < minIndent) {
            minIndent = indent
        }
    }

    // Strip the common leading whitespace from every non-blank line and then
    // re-indent the whole block by two spaces. Using `line.slice(strip)`
    // (instead of stripping ALL leading whitespace) preserves the relative
    // indentation between lines — including the case where minIndent is 0,
    // which would otherwise flatten any source that contains a top-level
    // line at column 0 (e.g. HOCON config files where a `}` closes at the
    // start of the line).
    const strip = minIndent ?? 0
    return lines
        .map((line) => {
            if (line.trim() === '') return ''
            return `  ${line.slice(strip)}`
        })
        .join('\n')
}

/** Strip common leading indent only; first line starts at column 0 (HOCON/config in RST). */
function baselineIndent(content) {
    const lines = content.split('\n')
    let minIndent = null
    for (const line of lines) {
        if (line.trim() === '') continue
        const indent = (line.match(/^(\s*)/) || ['', ''])[1].length
        if (minIndent === null || indent < minIndent) minIndent = indent
    }
    const strip = minIndent ?? 0
    return lines
        .map((line) => (line.trim() === '' ? '' : line.slice(strip)))
        .join('\n')
}

function applyIndentOption(content, normalizeIndentOption) {
    if (normalizeIndentOption === false) return content
    if (normalizeIndentOption === 'baseline') return baselineIndent(content)
    return normalizeIndent(content)
}

function trimBlankEdges(content) {
    return content.replace(/^\s*\n+/, '').replace(/\n+\s*$/, '')
}

function convertRstBlocksToMarkdown(content, fallbackLanguage = '') {
    const input = trimBlankEdges(content)
    const lines = input.split('\n')
    const out = []
    let i = 0

    while (i < lines.length) {
        const m = lines[i].match(/^\s*\.\.\s+code-block::\s*(\S*)\s*$/)
        if (!m) {
            i++
            continue
        }

        let language = (m[1] || '').trim()
        if (!language || language.toLowerCase() === 'none') {
            language = fallbackLanguage || ''
        }

        i++
        while (i < lines.length && lines[i].trim() === '') i++

        const block = []
        while (i < lines.length) {
            const line = lines[i]
            if (line.trim() === '') {
                block.push('')
                i++
                continue
            }

            if (/^( {4}|\t)/.test(line)) {
                block.push(line.replace(/^( {4}|\t)/, ''))
                i++
                continue
            }
            break
        }

        while (block.length > 0 && block[block.length - 1] === '') {
            block.pop()
        }

        if (language) {
            out.push(`\`\`\`${language}`)
        } else {
            out.push('```')
        }
        out.push(block.join('\n'))
        out.push('```')
        out.push('')
    }

    if (out.length === 0) {
        // Safety fallback: strip any leftover RST directives and keep only content.
        const cleaned = input
            .split('\n')
            .filter((line) => !/^\s*\.\.\s+code-block::/.test(line))
            .join('\n')
        const trimmed = trimBlankEdges(cleaned)
        const language = fallbackLanguage || ''
        if (language) {
            return `\`\`\`${language}\n${trimmed}\n\`\`\``
        }
        return `\`\`\`\n${trimmed}\n\`\`\``
    }

    while (out.length > 0 && out[out.length - 1] === '') out.pop()
    return out.join('\n')
}

function formatSnippetContent(content, options, globalOptions = {}) {
    let body = content
    if (options && options.unescapeRstQuotes) {
        body = body.replace(/\\'/g, "'")
    }
    if (options && options.transform === 'rstinclude') {
        return convertRstIncludeToMdx(body, {
            refTargets: {
                ...(globalOptions.rstIncludeRefTargets || {}),
                ...(options.refTargets || {}),
            },
        })
    }
    if (options && options.transform === 'rstjson') {
        const language = options && options.language ? options.language : ''
        return convertRstBlocksToMarkdown(body, language)
    }
    const displayStyle = (options && options.displayStyle) || 'wrapCode'
    const rawLanguage = options && options.language ? options.language : ''
    const language =
        rawLanguage && rawLanguage.toLowerCase() === 'none' ? '' : rawLanguage

    switch (displayStyle) {
        case 'wrapCode':
            if (language) {
                return `\`\`\`${language}\n${body}\n\`\`\``
            } else {
                return `\`\`\`\n${body}\n\`\`\``
            }

        default:
            return content
    }
}

function commentAttribute(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/--/g, '&#45;&#45;')
}

function formatLocation(location) {
    if (!location || !location.type) return 'unknown'

    switch (location.type) {
        case 'fullFile':
            return 'fullFile'
        case 'lines':
        case 'jsonIndex':
            return `${location.type}:${location.start}-${location.end}`
        case 'stringMarker':
        case 'regexWrap':
            return `${location.type}:${location.start}->${location.end}`
        default:
            return location.type
    }
}

function buildProvenanceComment(snippet) {
    const repo = snippet.sourceRepo || SOURCE_REPO_NAME
    const fields = [
        ['repo', repo],
        ['path', snippet.sourceFilepath],
        ['commit', SOURCE_COMMIT],
        ['snippet', snippet.snippetName],
        ['location', formatLocation(snippet.location)],
    ]
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([key, value]) => `${key}="${commentAttribute(value)}"`)
        .join(' ')

    return `<!-- source-snippet ${fields} -->`
}

function addProvenanceComment(content, snippet) {
    const comment = buildProvenanceComment(snippet)
    const lines = content.split('\n')
    let insertAt = 0

    while (insertAt < lines.length) {
        const line = lines[insertAt]
        if (line.trim() === '') {
            insertAt++
            continue
        }
        if (/^import\s/.test(line)) {
            insertAt++
            continue
        }
        break
    }

    lines.splice(insertAt, 0, comment)
    return lines.join('\n')
}

function getSourceFilePath(snippet) {
    if (snippet.sourceFilepath) {
        return path.join(REPO_ROOT, snippet.sourceFilepath)
    } else {
        throw new Error(
            `Snippet "${snippet.snippetName}" has no source file path specified`
        )
    }
}

function processSnippet(snippet, verbose, globalOptions = {}) {
    try {
        if (verbose) {
            console.log(`Processing snippet: ${snippet.snippetName}`)
        }

        if (!snippet.snippetName) {
            throw new Error('Snippet missing required field: snippetName')
        }

        if (!snippet.location) {
            throw new Error(
                `Snippet "${snippet.snippetName}" missing required field: location`
            )
        }

        const sourceFilePath = getSourceFilePath(snippet)

        const fileContent = readFileContent(sourceFilePath)

        const extractedContent = extractSnippetContent(
            fileContent,
            snippet.location
        )
        const skipTransform =
            snippet.options &&
            (snippet.options.transform === 'rstjson' ||
                snippet.options.transform === 'rstinclude')
        const indentOpt = snippet.options?.normalizeIndent
        const normalizedContent = skipTransform
            ? extractedContent
            : applyIndentOption(
                  extractedContent,
                  indentOpt === undefined ? true : indentOpt
              )

        const formattedContent = formatSnippetContent(
            normalizedContent,
            snippet.options || {},
            globalOptions
        )
        const contentWithProvenance = addProvenanceComment(
            formattedContent,
            snippet
        )

        const outputFileName = `${snippet.snippetName}.mdx`
        const outputPath = path.join(OUTPUT_FOLDER_PATH, outputFileName)
        const outputPathDir = path.dirname(outputPath)

        fs.mkdirSync(outputPathDir, { recursive: true })

        fs.writeFileSync(outputPath, contentWithProvenance, 'utf8')

        if (verbose) {
            console.log(`✓ Successfully extracted snippet to: ${outputPath}`)
        }
    } catch (error) {
        console.error(
            `✗ Error processing snippet "${snippet.snippetName}": ${error.message}`
        )
        throw error
    }
}

/**
 * Main function
 * Reads docs/config/exportConfig.json and processes each snippet.
 */
function main() {
    try {
        const verbose = process.argv.includes('--verbose')
        const configContent = readFileContent(EXPORT_CONFIG_PATH)
        const config = JSON.parse(configContent)

        if (!config.snippets || !Array.isArray(config.snippets)) {
            throw new Error(
                'exportConfig.json must have a top-level "snippets" array'
            )
        }

        let successCount = 0
        let errorCount = 0

        const globalOptions = {
            rstIncludeRefTargets: config.rstIncludeRefTargets || {},
        }

        for (const snippet of config.snippets) {
            try {
                processSnippet(snippet, verbose, globalOptions)
                successCount++
            } catch (error) {
                errorCount++
            }
        }

        console.log(
            `\nProcessing complete: ${successCount} succeeded, ${errorCount} failed`
        )

        if (errorCount > 0) {
            process.exit(1)
        }
    } catch (error) {
        console.error(`Fatal error: ${error.message}`)
        process.exit(1)
    }
}

main()
