import { describe, expect, it } from 'vitest'
import {
  collectOperations,
  collectSchemaRefs,
  DEFAULT_TAG_KEY,
  formatSchemaType,
  groupByTag,
  pickContentSchema,
  schemaFields,
  sortedResponseCodes,
} from '../openapi'
import type { OpenApiSpec } from '../../types/openapi'

const spec: OpenApiSpec = {
  openapi: '3.1.0',
  info: { title: 'Test API', version: '0.1.0' },
  paths: {
    '/api/tasks': {
      get: { tags: ['tasks'], summary: 'List tasks', responses: { '200': { description: 'ok' } } },
      post: { tags: ['tasks'], summary: 'Create task', responses: { '200': { description: 'ok' } } },
    },
    '/api/system/info': {
      get: { tags: ['system'], summary: 'System info', responses: { '200': { description: 'ok' } } },
    },
    '/api/legacy': {
      get: { summary: 'Untagged', responses: { '200': { description: 'ok' } } },
    },
  },
  components: {
    schemas: {
      TaskRead: {
        type: 'object',
        required: ['id'],
        properties: {
          id: { type: 'string', description: 'Task id' },
          status: { type: 'string', enum: ['running', 'succeeded'] },
          owner: { $ref: '#/components/schemas/TaskRead' },
        },
      },
    },
  },
}

describe('collectOperations', () => {
  it('flattens every path × method into a list with stable keys and tags', () => {
    const ops = collectOperations(spec)
    expect(ops).toHaveLength(4)
    expect(ops.map(o => o.key)).toEqual([
      'get /api/tasks',
      'post /api/tasks',
      'get /api/system/info',
      'get /api/legacy',
    ])
    expect(ops[3].tag).toBe(DEFAULT_TAG_KEY)
  })

  it('returns an empty list when the spec is missing', () => {
    expect(collectOperations(undefined)).toEqual([])
  })
})

describe('groupByTag', () => {
  it('buckets operations by first-seen tag order', () => {
    const groups = groupByTag(collectOperations(spec))
    expect(groups.map(g => g.tag)).toEqual(['tasks', 'system', DEFAULT_TAG_KEY])
    expect(groups[0].operations).toHaveLength(2)
  })
})

describe('formatSchemaType', () => {
  it('renders refs, arrays, unions, formats, and falls back to any', () => {
    expect(formatSchemaType({ $ref: '#/components/schemas/TaskRead' })).toBe('TaskRead')
    expect(formatSchemaType({ type: 'array', items: { $ref: '#/components/schemas/TaskRead' } })).toBe(
      'TaskRead[]',
    )
    expect(formatSchemaType({ anyOf: [{ type: 'string' }, { type: 'null' }] })).toBe('string | null')
    expect(formatSchemaType({ type: 'string', format: 'date-time' })).toBe('string<date-time>')
    expect(formatSchemaType({ type: 'integer' })).toBe('integer')
    expect(
      formatSchemaType({
        type: 'object',
        additionalProperties: { $ref: '#/components/schemas/TaskRead' },
      }),
    ).toBe('Record<string, TaskRead>')
    expect(formatSchemaType({ type: 'object', properties: {} })).toBe('object')
    expect(formatSchemaType(undefined)).toBe('any')
  })
})

describe('collectSchemaRefs', () => {
  it('collects surface-level refs through arrays, unions, and dict values', () => {
    expect(collectSchemaRefs({ $ref: '#/components/schemas/A' })).toEqual(['A'])
    expect(collectSchemaRefs({ type: 'array', items: { $ref: '#/components/schemas/A' } })).toEqual(['A'])
    expect(collectSchemaRefs({ anyOf: [{ $ref: '#/components/schemas/A' }, { type: 'null' }] })).toEqual([
      'A',
    ])
    expect(
      collectSchemaRefs({ type: 'object', additionalProperties: { $ref: '#/components/schemas/B' } }),
    ).toEqual(['B'])
    expect(collectSchemaRefs({ type: 'string' })).toEqual([])
  })
})

describe('schemaFields', () => {
  it('resolves a $ref to its top-level fields with required flags and enums', () => {
    const fields = schemaFields({ $ref: '#/components/schemas/TaskRead' }, spec)
    expect(fields.map(f => f.name)).toEqual(['id', 'status', 'owner'])
    expect(fields[0]).toMatchObject({ name: 'id', type: 'string', required: true })
    expect(fields[1].enumValues).toEqual(['running', 'succeeded'])
    // self-referential field renders as the model name without looping forever
    expect(fields[2].type).toBe('TaskRead')
    expect(fields[2].refs).toEqual(['TaskRead'])
  })

  it('sees through a top-level array to its element model fields', () => {
    const fields = schemaFields(
      { type: 'array', items: { $ref: '#/components/schemas/TaskRead' } },
      spec,
    )
    expect(fields.map(f => f.name)).toEqual(['id', 'status', 'owner'])
  })
})

describe('pickContentSchema', () => {
  it('prefers a JSON media type', () => {
    const picked = pickContentSchema({
      'text/plain': { schema: { type: 'string' } },
      'application/json': { schema: { $ref: '#/components/schemas/TaskRead' } },
    })
    expect(picked?.mediaType).toBe('application/json')
  })
})

describe('sortedResponseCodes', () => {
  it('orders 2xx first, then others ascending, default last', () => {
    expect(sortedResponseCodes({ '422': {}, '200': {}, default: {}, '404': {} })).toEqual([
      '200',
      '404',
      '422',
      'default',
    ])
  })
})
