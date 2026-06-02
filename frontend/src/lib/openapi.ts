import type {
  OpenApiMediaType,
  OpenApiOperation,
  OpenApiSchema,
  OpenApiSpec,
} from '../types/openapi'

export const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete', 'options', 'head'] as const
export type HttpMethod = (typeof HTTP_METHODS)[number]

/** Tag bucket for operations that declare no tag. */
export const DEFAULT_TAG_KEY = '__default__'

export interface ResolvedOperation {
  /** Stable identity, e.g. `"get /api/tasks"`. */
  key: string
  method: HttpMethod
  path: string
  tag: string
  summary: string
  deprecated: boolean
  operation: OpenApiOperation
}

export interface OperationGroup {
  tag: string
  operations: ResolvedOperation[]
}

/** Flatten `paths × methods` into a single ordered list of operations. */
export function collectOperations(spec: OpenApiSpec | undefined): ResolvedOperation[] {
  if (!spec?.paths) return []
  const out: ResolvedOperation[] = []
  for (const [path, item] of Object.entries(spec.paths)) {
    if (!item) continue
    for (const method of HTTP_METHODS) {
      const operation = item[method]
      if (!operation) continue
      out.push({
        key: `${method} ${path}`,
        method,
        path,
        tag: operation.tags?.[0] ?? DEFAULT_TAG_KEY,
        summary: operation.summary ?? operation.operationId ?? '',
        deprecated: Boolean(operation.deprecated),
        operation,
      })
    }
  }
  return out
}

/** Group operations by their first tag, preserving first-seen tag order. */
export function groupByTag(operations: ResolvedOperation[]): OperationGroup[] {
  const order: string[] = []
  const buckets = new Map<string, ResolvedOperation[]>()
  for (const op of operations) {
    let bucket = buckets.get(op.tag)
    if (!bucket) {
      bucket = []
      buckets.set(op.tag, bucket)
      order.push(op.tag)
    }
    bucket.push(op)
  }
  return order.map(tag => ({ tag, operations: buckets.get(tag)! }))
}

/** `"#/components/schemas/TaskRead"` -> `"TaskRead"`. */
export function refName(ref: string): string {
  return ref.split('/').pop() ?? ref
}

/**
 * Follow `$ref` / single-member `allOf` links to the underlying schema. Guards
 * against reference cycles so self-referential models don't loop forever.
 */
export function resolveSchema(
  schema: OpenApiSchema | undefined,
  spec: OpenApiSpec | undefined,
  seen: Set<string> = new Set(),
): OpenApiSchema | undefined {
  if (!schema) return undefined
  if (schema.$ref) {
    const name = refName(schema.$ref)
    if (seen.has(name)) return schema
    seen.add(name)
    return resolveSchema(spec?.components?.schemas?.[name], spec, seen)
  }
  if (schema.allOf?.length === 1 && !schema.properties) {
    return resolveSchema(schema.allOf[0], spec, seen)
  }
  return schema
}

/**
 * Short, human-readable type label: `string`, `TaskRead`, `TaskRead[]`,
 * `string | null`, `string<date-time>`, etc. Does not resolve refs — it shows
 * the referenced model name, which is what a reference table wants.
 */
export function formatSchemaType(schema: OpenApiSchema | undefined): string {
  if (!schema) return 'any'
  if (schema.$ref) return refName(schema.$ref)
  if (schema.allOf?.length) {
    return schema.allOf.map(formatSchemaType).join(' & ')
  }
  const union = schema.anyOf ?? schema.oneOf
  if (union?.length) {
    return Array.from(new Set(union.map(formatSchemaType))).join(' | ')
  }
  const type = Array.isArray(schema.type) ? schema.type.join(' | ') : schema.type
  if (type === 'array') {
    return `${formatSchemaType(schema.items)}[]`
  }
  if (type === 'object' || schema.properties || schema.additionalProperties) {
    const additional = schema.additionalProperties
    if (additional && typeof additional === 'object') {
      return `Record<string, ${formatSchemaType(additional)}>`
    }
    return 'object'
  }
  if (type) {
    return schema.format ? `${type}<${schema.format}>` : type
  }
  return 'any'
}

/**
 * Collect the named component models a field's type references at the surface
 * level — seeing through arrays, unions, and dict values, but NOT into the
 * referenced models themselves. Powers click-to-expand drill-down.
 */
export function collectSchemaRefs(schema: OpenApiSchema | undefined): string[] {
  const out: string[] = []
  const walk = (node: OpenApiSchema | undefined, depth: number) => {
    if (!node || depth > 4) return
    if (node.$ref) {
      out.push(refName(node.$ref))
      return
    }
    walk(node.items, depth + 1)
    for (const sub of node.allOf ?? []) walk(sub, depth + 1)
    for (const sub of node.anyOf ?? []) walk(sub, depth + 1)
    for (const sub of node.oneOf ?? []) walk(sub, depth + 1)
    if (node.additionalProperties && typeof node.additionalProperties === 'object') {
      walk(node.additionalProperties, depth + 1)
    }
  }
  walk(schema, 0)
  return Array.from(new Set(out))
}

export function enumValues(schema: OpenApiSchema | undefined): string[] | undefined {
  if (!schema?.enum?.length) return undefined
  return schema.enum.map(value => (typeof value === 'string' ? value : JSON.stringify(value)))
}

export interface SchemaField {
  name: string
  type: string
  required: boolean
  description?: string
  enumValues?: string[]
  /** Named component models this field's type references, for drill-down. */
  refs: string[]
}

/** Resolve an (optionally `$ref`'d) object schema to its top-level fields. */
export function schemaFields(
  schema: OpenApiSchema | undefined,
  spec: OpenApiSpec | undefined,
): SchemaField[] {
  let resolved = resolveSchema(schema, spec)
  // See through a top-level array to its element model so list responses still
  // surface the element's fields rather than an empty table.
  const resolvedTypes = Array.isArray(resolved?.type) ? resolved.type : [resolved?.type]
  if (resolved && resolvedTypes.includes('array')) {
    resolved = resolveSchema(resolved.items, spec)
  }
  if (!resolved?.properties) return []
  const required = new Set(resolved.required ?? [])
  return Object.entries(resolved.properties).map(([name, prop]) => ({
    name,
    type: formatSchemaType(prop),
    required: required.has(name),
    description: typeof prop.description === 'string' ? prop.description : undefined,
    enumValues: enumValues(prop),
    refs: collectSchemaRefs(prop),
  }))
}

/** Pick the most relevant media type from a content map, preferring JSON. */
export function pickContentSchema(
  content: Record<string, OpenApiMediaType> | undefined,
): { mediaType: string; schema?: OpenApiSchema } | undefined {
  if (!content) return undefined
  const keys = Object.keys(content)
  if (keys.length === 0) return undefined
  const mediaType = keys.find(key => key.includes('json')) ?? keys[0]
  return { mediaType, schema: content[mediaType]?.schema }
}

/** Order response codes: 2xx first, then other statuses ascending, `default` last. */
export function sortedResponseCodes(responses: Record<string, unknown> | undefined): string[] {
  if (!responses) return []
  const rank = (code: string) => (code.startsWith('2') ? 0 : code === 'default' ? 2 : 1)
  return Object.keys(responses).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
}
