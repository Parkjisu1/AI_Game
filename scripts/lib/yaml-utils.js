/**
 * yaml-utils.js - Shared YAML parser for Design Workflow scripts
 * Replaces 6 inconsistent custom parsers with one robust implementation.
 *
 * Supports the YAML subset used across all scripts:
 *   - Nested key-value mappings
 *   - Block sequences (- item) with nested objects
 *   - Block scalars (| literal, > folded)
 *   - Inline arrays [a, b, c]
 *   - Quoted strings, comments, document markers ---
 *
 * Falls back to js-yaml if available for full spec compliance.
 *
 * Usage:
 *   const { parseYaml, serializeYaml } = require('./lib/yaml-utils');
 *   const data = parseYaml(yamlText);
 *   const yamlText = serializeYaml(obj);
 */

'use strict';

// ---------------------------------------------------------------------------
// Try js-yaml first, fall back to built-in
// ---------------------------------------------------------------------------
let jsYaml = null;
try { jsYaml = require('js-yaml'); } catch { /* not installed, use built-in */ }

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Parse YAML text into a JS object.
 * @param {string} text - YAML content
 * @returns {*} Parsed object/array/scalar
 */
function parseYaml(text) {
  if (!text || typeof text !== 'string') return null;

  // Strip BOM
  text = text.replace(/^\uFEFF/, '');

  // Strip markdown code fences
  text = text.replace(/^```(?:yaml|yml)?\s*\n?/m, '').replace(/\n?\s*```\s*$/m, '');

  if (jsYaml) {
    try {
      return jsYaml.load(text);
    } catch (e) {
      // Fall through to built-in parser
    }
  }
  return parseBuiltIn(text);
}

/**
 * Serialize a JS object to YAML text.
 * @param {*} obj - Object to serialize
 * @returns {string} YAML text
 */
function serializeYaml(obj) {
  if (jsYaml) {
    try {
      return jsYaml.dump(obj, { lineWidth: -1, noRefs: true, sortKeys: false });
    } catch { /* fall through */ }
  }
  return serializeBuiltIn(obj, 0);
}

module.exports = { parseYaml, serializeYaml };

// ---------------------------------------------------------------------------
// Built-in YAML parser
// ---------------------------------------------------------------------------

function parseBuiltIn(text) {
  const lines = text.split(/\r?\n/);
  const root = {};
  // Stack: { obj, indent, lastKey, lastArray }
  const stack = [{ obj: root, indent: -2, lastKey: null, lastArray: null }];

  let i = 0;
  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trim();

    // Skip blanks, comments, document markers
    if (!trimmed || trimmed.startsWith('#') || trimmed === '---' || trimmed === '...') {
      i++;
      continue;
    }

    const indent = raw.length - raw.trimStart().length;

    // --- Block scalar continuation check ---
    // Handled inside the key-value branch below

    // --- Pop stack to correct level ---
    while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }

    const frame = stack[stack.length - 1];

    // --- List item ---
    if (trimmed.startsWith('- ')) {
      const itemContent = trimmed.slice(2);
      i = handleListItem(lines, i, indent, itemContent, frame, stack);
      continue;
    }
    if (trimmed === '-') {
      // Empty list item → nested object
      i = handleListItem(lines, i, indent, '', frame, stack);
      continue;
    }

    // --- Key: value ---
    const colonIdx = findKeyColon(trimmed);
    if (colonIdx !== -1) {
      const key = trimmed.slice(0, colonIdx).trim().replace(/^['"]|['"]$/g, '');
      const rest = trimmed.slice(colonIdx + 1).trim();

      frame.lastKey = key;
      frame.lastArray = null;

      if (rest === '|' || rest === '|+' || rest === '|-') {
        // Literal block scalar
        const blockResult = collectBlockScalar(lines, i + 1, indent, 'literal');
        frame.obj[key] = blockResult.text;
        i = blockResult.nextIndex;
        continue;
      }
      if (rest === '>' || rest === '>+' || rest === '>-') {
        // Folded block scalar
        const blockResult = collectBlockScalar(lines, i + 1, indent, 'folded');
        frame.obj[key] = blockResult.text;
        i = blockResult.nextIndex;
        continue;
      }
      if (rest === '' || rest === '{}') {
        if (rest === '{}') {
          frame.obj[key] = {};
          i++;
          continue;
        }
        // Peek next non-blank line to determine if list or nested object
        const nextInfo = peekNextContent(lines, i + 1);
        if (nextInfo && nextInfo.trimmed.startsWith('- ')) {
          // Array
          frame.obj[key] = [];
          frame.lastArray = frame.obj[key];
          i++;
          continue;
        } else {
          // Nested object
          frame.obj[key] = {};
          stack.push({ obj: frame.obj[key], indent, lastKey: null, lastArray: null });
          i++;
          continue;
        }
      }
      if (rest === '[]') {
        frame.obj[key] = [];
        frame.lastArray = frame.obj[key];
        i++;
        continue;
      }

      // Inline value
      frame.obj[key] = parseInlineValue(rest);
      i++;
      continue;
    }

    // Unknown line, skip
    i++;
  }

  return root;
}

/**
 * Handle a list item (- ...).
 * Returns the next line index to process.
 */
function handleListItem(lines, lineIdx, indent, content, frame, stack) {
  // Find or create the array to push into
  let arr = frame.lastArray;
  if (!arr) {
    // Try to use parent's lastKey
    if (frame.lastKey && frame.obj[frame.lastKey] !== undefined) {
      if (!Array.isArray(frame.obj[frame.lastKey])) {
        frame.obj[frame.lastKey] = [];
      }
      arr = frame.obj[frame.lastKey];
      frame.lastArray = arr;
    } else {
      // No context for this list item — skip
      return lineIdx + 1;
    }
  }

  const trimmedContent = content.trim();

  if (trimmedContent === '' || trimmedContent === '{}') {
    // Empty item → create a new nested object
    const newObj = {};
    arr.push(newObj);
    stack.push({ obj: newObj, indent, lastKey: null, lastArray: null });
    return lineIdx + 1;
  }

  // Check if the item has inline key: value (e.g., "- id: foo")
  const colonIdx = findKeyColon(trimmedContent);
  if (colonIdx !== -1) {
    const key = trimmedContent.slice(0, colonIdx).trim();
    const val = trimmedContent.slice(colonIdx + 1).trim();
    const newObj = {};
    newObj[key] = (val === '') ? {} : parseInlineValue(val);
    arr.push(newObj);
    stack.push({ obj: newObj, indent, lastKey: key, lastArray: null });
    return lineIdx + 1;
  }

  // Scalar list item
  arr.push(parseScalar(trimmedContent));
  return lineIdx + 1;
}

/**
 * Collect a block scalar (literal | or folded >).
 * Returns { text, nextIndex }.
 */
function collectBlockScalar(lines, startIdx, keyIndent, mode) {
  const contentLines = [];
  let blockIndent = -1;
  let i = startIdx;

  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trim();

    // Blank lines are part of block scalar content
    if (trimmed === '') {
      contentLines.push('');
      i++;
      continue;
    }

    const lineIndent = raw.length - raw.trimStart().length;

    // First content line establishes the block indent
    if (blockIndent === -1) {
      if (lineIndent <= keyIndent) {
        // No content — empty block
        break;
      }
      blockIndent = lineIndent;
    }

    if (lineIndent < blockIndent) {
      break;
    }

    // Strip the block indent from content
    contentLines.push(raw.slice(blockIndent));
    i++;
  }

  // Trim trailing blank lines
  while (contentLines.length > 0 && contentLines[contentLines.length - 1] === '') {
    contentLines.pop();
  }

  let text;
  if (mode === 'literal') {
    text = contentLines.join('\n');
  } else {
    // Folded: join consecutive non-blank lines with spaces, preserve blank line breaks
    const paragraphs = [];
    let current = [];
    for (const line of contentLines) {
      if (line === '') {
        if (current.length > 0) paragraphs.push(current.join(' '));
        paragraphs.push('');
        current = [];
      } else {
        current.push(line);
      }
    }
    if (current.length > 0) paragraphs.push(current.join(' '));
    text = paragraphs.join('\n');
  }

  return { text, nextIndex: i };
}

/**
 * Find the colon separating key from value.
 * Returns -1 if not a valid key: value line.
 * Handles quoted keys and URLs (colons inside values).
 */
function findKeyColon(trimmed) {
  // Skip if it looks like a bare URL or timestamp
  if (/^https?:/.test(trimmed)) return -1;

  let inQuote = null;
  for (let i = 0; i < trimmed.length; i++) {
    const ch = trimmed[i];
    if (ch === '"' || ch === "'") {
      if (inQuote === ch) inQuote = null;
      else if (!inQuote) inQuote = ch;
    }
    if (ch === ':' && !inQuote) {
      // Must be followed by space, end of string, or be at end
      if (i + 1 >= trimmed.length || trimmed[i + 1] === ' ' || trimmed[i + 1] === '\t') {
        return i;
      }
    }
  }
  return -1;
}

/**
 * Parse an inline YAML value (after the colon).
 */
function parseInlineValue(raw) {
  if (!raw) return null;
  const trimmed = raw.trim();

  // Inline array: [a, b, c]
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    return parseInlineArray(trimmed);
  }

  // Inline object: {a: 1, b: 2}
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    return parseInlineObject(trimmed);
  }

  return parseScalar(trimmed);
}

/**
 * Parse inline array: [a, b, c]
 */
function parseInlineArray(raw) {
  const inner = raw.slice(1, -1).trim();
  if (!inner) return [];

  // Try JSON first
  try {
    return JSON.parse(raw.replace(/'/g, '"'));
  } catch { /* continue with manual parse */ }

  const items = splitComma(inner);
  return items.map(item => parseScalar(item.trim()));
}

/**
 * Parse inline object: {a: 1, b: 2}
 */
function parseInlineObject(raw) {
  const inner = raw.slice(1, -1).trim();
  if (!inner) return {};

  const obj = {};
  const pairs = splitComma(inner);
  for (const pair of pairs) {
    const ci = pair.indexOf(':');
    if (ci !== -1) {
      const k = pair.slice(0, ci).trim().replace(/^['"]|['"]$/g, '');
      const v = pair.slice(ci + 1).trim();
      obj[k] = parseScalar(v);
    }
  }
  return obj;
}

/**
 * Split by comma, respecting quotes and brackets.
 */
function splitComma(str) {
  const result = [];
  let depth = 0;
  let inQuote = null;
  let current = '';

  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (ch === '"' || ch === "'") {
      if (inQuote === ch) inQuote = null;
      else if (!inQuote) inQuote = ch;
    }
    if (!inQuote) {
      if (ch === '[' || ch === '{') depth++;
      if (ch === ']' || ch === '}') depth--;
    }
    if (ch === ',' && !inQuote && depth === 0) {
      result.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  if (current) result.push(current);
  return result;
}

/**
 * Parse a scalar YAML value.
 */
function parseScalar(val) {
  if (val === undefined || val === null) return null;
  const trimmed = (typeof val === 'string') ? val.trim() : String(val);
  if (trimmed === '') return '';
  if (trimmed === 'true' || trimmed === 'True' || trimmed === 'TRUE') return true;
  if (trimmed === 'false' || trimmed === 'False' || trimmed === 'FALSE') return false;
  if (trimmed === 'null' || trimmed === 'Null' || trimmed === 'NULL' || trimmed === '~') return null;

  // Remove surrounding quotes
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }

  // Try number
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  if (/^-?\d+(\.\d+)?[eE][+-]?\d+$/.test(trimmed)) return Number(trimmed);

  return trimmed;
}

/**
 * Peek at the next non-blank line.
 */
function peekNextContent(lines, startIdx) {
  for (let i = startIdx; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed && !trimmed.startsWith('#')) {
      return { trimmed, indent: lines[i].length - lines[i].trimStart().length, index: i };
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Built-in YAML serializer
// ---------------------------------------------------------------------------

function serializeBuiltIn(obj, indent) {
  const pad = '  '.repeat(indent);
  let out = '';

  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]\n';
    for (const item of obj) {
      if (typeof item === 'object' && item !== null && !Array.isArray(item)) {
        const keys = Object.keys(item);
        if (keys.length > 0) {
          // First key on same line as dash
          const firstKey = keys[0];
          const firstVal = item[firstKey];
          if (isSimpleValue(firstVal)) {
            out += `${pad}- ${firstKey}: ${scalarToYaml(firstVal)}\n`;
          } else {
            out += `${pad}- ${firstKey}:\n`;
            out += serializeBuiltIn(firstVal, indent + 2);
          }
          // Remaining keys indented
          for (let k = 1; k < keys.length; k++) {
            const key = keys[k];
            const val = item[key];
            if (isSimpleValue(val)) {
              out += `${pad}  ${key}: ${scalarToYaml(val)}\n`;
            } else if (Array.isArray(val) && val.length === 0) {
              out += `${pad}  ${key}: []\n`;
            } else {
              out += `${pad}  ${key}:\n`;
              out += serializeBuiltIn(val, indent + 2);
            }
          }
        } else {
          out += `${pad}- {}\n`;
        }
      } else if (Array.isArray(item)) {
        out += `${pad}-\n`;
        out += serializeBuiltIn(item, indent + 1);
      } else {
        out += `${pad}- ${scalarToYaml(item)}\n`;
      }
    }
  } else if (typeof obj === 'object' && obj !== null) {
    for (const [key, val] of Object.entries(obj)) {
      if (isSimpleValue(val)) {
        out += `${pad}${key}: ${scalarToYaml(val)}\n`;
      } else if (Array.isArray(val) && val.length === 0) {
        out += `${pad}${key}: []\n`;
      } else {
        out += `${pad}${key}:\n`;
        out += serializeBuiltIn(val, indent + 1);
      }
    }
  } else {
    out += `${pad}${scalarToYaml(obj)}\n`;
  }

  return out;
}

function isSimpleValue(val) {
  return val === null || val === undefined ||
    typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean';
}

function scalarToYaml(val) {
  if (val === null || val === undefined) return 'null';
  if (typeof val === 'boolean') return String(val);
  if (typeof val === 'number') return String(val);
  const str = String(val);
  // Quote strings that contain special chars or look like YAML special values
  if (str === '' ||
      /[:{}\[\],&*#?|<>=!%@`\n]/.test(str) ||
      /^[-\s]/.test(str) ||
      /^(true|false|null|yes|no|on|off|True|False|Null)$/i.test(str) ||
      /^\d/.test(str)) {
    return `"${str.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n')}"`;
  }
  return str;
}
