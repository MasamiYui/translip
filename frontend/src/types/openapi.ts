// Minimal subset of the OpenAPI 3.x object model — only the fields the in-app
// API reference renders. The backend emits the full spec; unknown fields are
// simply ignored here.

export interface OpenApiSpec {
  openapi: string
  info: OpenApiInfo
  paths: Record<string, OpenApiPathItem>
  components?: { schemas?: Record<string, OpenApiSchema> }
  tags?: { name: string; description?: string }[]
}

export interface OpenApiInfo {
  title: string
  version: string
  description?: string
}

export type OpenApiPathItem = Partial<Record<string, OpenApiOperation>>

export interface OpenApiOperation {
  tags?: string[]
  summary?: string
  description?: string
  operationId?: string
  deprecated?: boolean
  parameters?: OpenApiParameter[]
  requestBody?: OpenApiRequestBody
  responses?: Record<string, OpenApiResponse>
}

export interface OpenApiParameter {
  name: string
  in: 'path' | 'query' | 'header' | 'cookie'
  required?: boolean
  description?: string
  deprecated?: boolean
  schema?: OpenApiSchema
}

export interface OpenApiRequestBody {
  description?: string
  required?: boolean
  content?: Record<string, OpenApiMediaType>
}

export interface OpenApiResponse {
  description?: string
  content?: Record<string, OpenApiMediaType>
}

export interface OpenApiMediaType {
  schema?: OpenApiSchema
}

export interface OpenApiSchema {
  $ref?: string
  type?: string | string[]
  format?: string
  title?: string
  description?: string
  enum?: unknown[]
  default?: unknown
  items?: OpenApiSchema
  properties?: Record<string, OpenApiSchema>
  required?: string[]
  anyOf?: OpenApiSchema[]
  oneOf?: OpenApiSchema[]
  allOf?: OpenApiSchema[]
  additionalProperties?: boolean | OpenApiSchema
  [key: string]: unknown
}
