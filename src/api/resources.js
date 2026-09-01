/* ============================================================
   One hook per resource.

   Pages call these instead of building paths, so a route that
   moves is changed in one file rather than in twenty. Each read
   hook returns the `{ data, error, loading, reload }` shape that
   `<Async>` consumes; each write returns `[run, { loading }]`.

   `qs()` drops empty and "all" values, so the default state of
   every filter bar produces a clean `/campaigns` rather than
   `/campaigns?q=&status=all&type=all`.
   ============================================================ */

import { api, qs } from './client'
import { invalidate, useApi, useMutation } from './hooks'

/* ---------------------------------------------------------------- reads */

export const useOverview = (range = 30) => useApi(`/stats/overview?range=${range}`)
export const useSeries = (range = 30) => useApi(`/stats/series?range=${range}`)
export const useFunnel = () => useApi('/stats/funnel')
export const useHeatmap = () => useApi('/stats/heatmap')
export const useCohorts = () => useApi('/stats/cohorts')
export const useDevices = () => useApi('/stats/devices')
export const useTopCampaigns = (limit = 5) => useApi(`/stats/top-campaigns?limit=${limit}`)
export const useBreakdown = (dim, metric) => useApi(`/stats/breakdown${qs({ dim, metric })}`)
export const useEvents = (limit = 12) => useApi(`/events?limit=${limit}`)
export const useRecommendations = () => useApi('/recommendations')
export const useDeliverability = () => useApi('/deliverability')

export const useCampaigns = (params) => useApi(`/campaigns${qs(params)}`)
export const useCampaign = (id) => useApi(id ? `/campaigns/${id}` : null)

export const useContacts = (params) => useApi(`/contacts${qs(params)}`)
export const useContact = (id) => useApi(id ? `/contacts/${id}` : null)
export const useContactStats = () => useApi('/contacts/stats')

export const useSegments = () => useApi('/segments')
/* Who a campaign actually reached, and what happened to each one. Polled while
   a send drains, which is why it takes the page rather than fetching it all. */
export const useRecipients = (id, params) =>
  useApi(id ? `/campaigns/${id}/recipients${qs(params)}` : null)
export const useSegmentPreview = (id) => useApi(id ? `/segments/${id}/preview` : null)

export const useSuppression = (params) => useApi(`/suppression${qs(params)}`)

export const useAgents = () => useApi('/agents')
export const useAgent = (id) => useApi(id ? `/agents/${id}` : null)
export const useAgentTools = () => useApi('/agents/tools')

export const useInbox = (params) => useApi(`/inbox${qs(params)}`)
export const useExperiments = () => useApi('/experiments')
export const useJourneys = () => useApi('/journeys')

export const useTemplates = (category) => useApi(`/templates${qs({ category })}`)
export const useIntegrations = () => useApi('/integrations')
export const useKnowledge = () => useApi('/knowledge')
export const useDomains = () => useApi('/domains')
export const useTeam = () => useApi('/team')
export const useBilling = () => useApi('/billing')
export const useApiKeys = () => useApi('/api-keys')
export const useWebhooks = () => useApi('/webhooks')
export const useWebhookEvents = () => useApi('/webhooks/events')
export const useActivity = (params) => useApi(`/activity${qs(params)}`)
export const useNotifications = () => useApi('/notifications')
export const useSettings = () => useApi('/settings')
export const useMeta = () => useApi('/meta')

/* ---------------------------------------------------------------- writes

   Every mutation names the prefixes it invalidates. Getting this list right
   is what stops the panel showing a stale figure next to a fresh one — e.g.
   sending a campaign changes both the list AND the dashboard totals. */

export const useCreateCampaign = () =>
  useMutation((body) => api.post('/campaigns', body), { invalidates: ['/campaigns', '/stats', '/activity'] })

export const useUpdateCampaign = () =>
  useMutation(({ id, ...body }) => api.patch(`/campaigns/${id}`, body), { invalidates: ['/campaigns'] })

export const useDeleteCampaign = () =>
  useMutation((id) => api.del(`/campaigns/${id}`), { invalidates: ['/campaigns', '/stats', '/activity'] })

export const useSendCampaign = () =>
  useMutation(({ id, ...body }) => api.post(`/campaigns/${id}/send`, body), {
    invalidates: ['/campaigns', '/stats', '/activity', '/events'],
  })

export const useCampaignAction = () =>
  useMutation(({ id, action }) => api.post(`/campaigns/${id}/${action}`), {
    invalidates: ['/campaigns', '/stats', '/activity'],
  })

/* Pulls new replies out of Gmail and into the threads list. A button, not a
   poll: Gmail's push notifications need a Cloud Pub/Sub topic and a public
   webhook, which is a lot of infrastructure to ask an implementer to stand up
   so that a screen can refresh itself. */
/* Carries out an action the agent proposed and a person approved. The
   signature goes back untouched — the server checks that what is being
   confirmed is what was shown. */
export const useConfirmAction = () =>
  useMutation((body) => api.post('/ai/confirm', body), {
    invalidates: ['/contacts', '/campaigns', '/stats', '/activity', '/inbox'],
  })

export const useSyncReplies = () =>
  useMutation(() => api.post('/google/sync'), { invalidates: ['/inbox', '/activity'] })

export const useCreateContact = () =>
  useMutation((body) => api.post('/contacts', body), { invalidates: ['/contacts', '/segments'] })

export const useUpdateContact = () =>
  useMutation(({ id, ...body }) => api.patch(`/contacts/${id}`, body), {
    // a status change can add or remove a suppression, so that list moves too
    invalidates: ['/contacts', '/suppression', '/segments'],
  })

export const useDeleteContact = () =>
  useMutation((id) => api.del(`/contacts/${id}`), { invalidates: ['/contacts', '/segments'] })

export const useImportContacts = () =>
  useMutation((body) => api.post('/contacts/import', body), {
    invalidates: ['/contacts', '/segments', '/activity'],
  })

export const useCreateSegment = () =>
  useMutation((body) => api.post('/segments', body), { invalidates: ['/segments', '/activity'] })

export const useUpdateSegment = () =>
  useMutation(({ id, ...body }) => api.patch(`/segments/${id}`, body), { invalidates: ['/segments'] })

export const useDeleteSegment = () =>
  useMutation((id) => api.del(`/segments/${id}`), { invalidates: ['/segments'] })

export const useAddSuppression = () =>
  useMutation((body) => api.post('/suppression', body), { invalidates: ['/suppression', '/contacts'] })

export const useRemoveSuppression = () =>
  useMutation((id) => api.del(`/suppression/${id}`), { invalidates: ['/suppression', '/contacts'] })

export const useUpdateAgent = () =>
  useMutation(({ id, ...body }) => api.patch(`/agents/${id}`, body), { invalidates: ['/agents'] })

export const useAgentAction = () =>
  useMutation(({ id, action }) => api.post(`/agents/${id}/${action}`), {
    invalidates: ['/agents', '/activity'],
  })

export const useReply = () =>
  useMutation(({ id, ...body }) => api.post(`/inbox/${id}/reply`, body), {
    invalidates: ['/inbox', '/suppression', '/activity'],
  })

export const usePromoteExperiment = () =>
  useMutation((id) => api.post(`/experiments/${id}/promote`), {
    invalidates: ['/experiments', '/activity'],
  })

export const useJourneyAction = () =>
  useMutation(({ id, action }) => api.post(`/journeys/${id}/${action}`), { invalidates: ['/journeys'] })

export const useToggleIntegration = () =>
  useMutation(({ id, on }) => api.patch(`/integrations/${id}`, { on }), {
    invalidates: ['/integrations', '/activity'],
  })

export const useUpdateSettings = () =>
  useMutation((body) => api.patch('/settings', body), { invalidates: ['/settings'] })

export const useUpdateVoice = () =>
  useMutation((body) => api.patch('/knowledge/voice', body), { invalidates: ['/knowledge'] })

export const useAddDomain = () =>
  useMutation((body) => api.post('/domains', body), { invalidates: ['/domains', '/deliverability'] })

export const useVerifyDomain = () =>
  useMutation((id) => api.post(`/domains/${id}/verify`), {
    invalidates: ['/domains', '/deliverability', '/activity'],
  })

export const useInviteMember = () =>
  useMutation((body) => api.post('/team', body), { invalidates: ['/team', '/activity'] })

export const useChangeRole = () =>
  useMutation(({ id, role }) => api.patch(`/team/${id}`, { role }), { invalidates: ['/team', '/activity'] })

export const useRemoveMember = () =>
  useMutation((id) => api.del(`/team/${id}`), { invalidates: ['/team', '/activity'] })

export const useUpdateWebhook = () =>
  useMutation(({ id, ...body }) => api.patch(`/webhooks/${id}`, body), { invalidates: ['/webhooks'] })

export const useCreateWebhook = () =>
  useMutation((body) => api.post('/webhooks', body), { invalidates: ['/webhooks'] })

export const useCreateKey = () =>
  useMutation((body) => api.post('/api-keys', body), { invalidates: ['/api-keys', '/activity'] })

export const useRevokeKey = () =>
  useMutation((id) => api.del(`/api-keys/${id}`), { invalidates: ['/api-keys', '/activity'] })

/* The panel's single input. Invalidated broadly on purpose: one sentence can
   spend credits, write an activity row, and change what the home screen says. */
export const useAsk = () =>
  useMutation((body) => api.post('/ai/ask', body), { invalidates: ['/billing', '/activity'] })

export const useResearch = () =>
  useMutation((body) => api.post('/ai/research', body), { invalidates: ['/billing'] })

export const useCompose = () =>
  useMutation((body) => api.post('/ai/compose', body), { invalidates: ['/billing'] })

export const useAskSegment = () =>
  useMutation((body) => api.post('/ai/segment', body), { invalidates: ['/billing'] })

export const useActOnRecommendation = () =>
  useMutation(({ id, action }) => api.post(`/recommendations/${id}/${action}`), {
    invalidates: ['/recommendations'],
  })

export const useMarkNotificationsRead = () =>
  useMutation(() => api.post('/notifications/read'), { invalidates: ['/notifications'] })

export { invalidate }
