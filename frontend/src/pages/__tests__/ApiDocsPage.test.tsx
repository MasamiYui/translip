import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/I18nProvider'
import { ApiDocsPage } from '../ApiDocsPage'
import type { OpenApiSpec } from '../../types/openapi'

const apiMocks = vi.hoisted(() => ({
  getSpec: vi.fn(),
}))

vi.mock('../../api/api-docs', () => ({
  apiDocsApi: apiMocks,
}))

const spec: OpenApiSpec = {
  openapi: '3.1.0',
  info: { title: 'Translip — Pipeline Manager', version: '0.1.0' },
  paths: {
    '/api/tasks': {
      get: {
        tags: ['tasks'],
        summary: 'List tasks',
        parameters: [
          { name: 'page', in: 'query', required: false, schema: { type: 'integer' } },
        ],
        responses: {
          '200': {
            description: 'ok',
            content: { 'application/json': { schema: { $ref: '#/components/schemas/TaskRead' } } },
          },
        },
      },
    },
    '/api/system/info': {
      get: { tags: ['system'], summary: 'System info', responses: { '200': { description: 'ok' } } },
    },
  },
  components: {
    schemas: {
      TaskRead: {
        type: 'object',
        required: ['id'],
        properties: {
          id: { type: 'string' },
          status: { type: 'string' },
          owner: { $ref: '#/components/schemas/Owner' },
        },
      },
      Owner: {
        type: 'object',
        properties: { displayName: { type: 'string' } },
      },
    },
  },
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ApiDocsPage', () => {
  it('groups the live spec by tag and renders endpoints under each group', async () => {
    apiMocks.getSpec.mockResolvedValue(spec)
    render(<ApiDocsPage />, { wrapper: createWrapper() })

    // Groups default open, so endpoint rows are visible immediately.
    expect(await screen.findByText('List tasks')).toBeInTheDocument()
    expect(screen.getByText('System info')).toBeInTheDocument()
    expect(screen.getByText('/api/tasks')).toBeInTheDocument()
    expect(screen.getByTestId('api-docs-group-tasks')).toBeInTheDocument()
    expect(screen.getByTestId('api-docs-group-system')).toBeInTheDocument()
  })

  it('reveals parameters and response schema when an operation is expanded', async () => {
    apiMocks.getSpec.mockResolvedValue(spec)
    render(<ApiDocsPage />, { wrapper: createWrapper() })

    fireEvent.click(await screen.findByText('List tasks'))

    // Request parameter and the resolved response model field both surface.
    expect(await screen.findByText('page')).toBeInTheDocument()
    expect(screen.getByText('id')).toBeInTheDocument()
  })

  it('drills into a nested model when its type is clicked', async () => {
    apiMocks.getSpec.mockResolvedValue(spec)
    render(<ApiDocsPage />, { wrapper: createWrapper() })

    fireEvent.click(await screen.findByText('List tasks'))

    // The nested-model field is listed, but its inner fields are not yet shown.
    expect(await screen.findByText('owner')).toBeInTheDocument()
    expect(screen.queryByText('displayName')).not.toBeInTheDocument()

    // Clicking the model type drills in and reveals the nested fields.
    fireEvent.click(screen.getByRole('button', { name: /Owner/ }))
    expect(await screen.findByText('displayName')).toBeInTheDocument()
  })

  it('filters operations by the search box', async () => {
    apiMocks.getSpec.mockResolvedValue(spec)
    render(<ApiDocsPage />, { wrapper: createWrapper() })

    fireEvent.change(await screen.findByTestId('api-docs-search'), {
      target: { value: 'system' },
    })

    expect(screen.getByText('System info')).toBeInTheDocument()
    expect(screen.queryByText('List tasks')).not.toBeInTheDocument()
  })

  it('shows an error state with a retry action when the spec fails to load', async () => {
    apiMocks.getSpec.mockRejectedValue(new Error('boom'))
    render(<ApiDocsPage />, { wrapper: createWrapper() })

    await waitFor(() => expect(screen.getByTestId('api-docs-error')).toBeInTheDocument())
  })
})
