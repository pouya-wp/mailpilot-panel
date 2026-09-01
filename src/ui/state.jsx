/* ============================================================
   Loading, error and empty — the three states every page that
   talks to a server has to render, and the three that usually get
   skipped until something breaks in front of a customer.

   `Async` wraps the lot so a page reads as one expression:

     <Async {...q}>{(data) => <Table rows={data.items} />}</Async>

   Two decisions worth naming:

   * a RELOAD does not blank the page. If we already have data and
     a refetch is in flight, the old data stays and dims. Throwing
     the table away and showing a skeleton on every filter change
     makes the layout jump and loses the reader's place.
   * an error offers a retry and shows the request id. "Something
     went wrong" with no id is unactionable for whoever has to look
     at the log afterwards.
   ============================================================ */

import { useI18n } from '../i18n'
import { Button, EmptyState } from './index'
import { IcRefresh, IcWarn } from '../components/NavIcons'

export function Skeleton({ rows = 5, height = 5.6 }) {
  return (
    <div className="skel" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="skel__row" style={{ height: `${height}rem`, animationDelay: `${i * 0.07}s` }} />
      ))}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  const { t } = useI18n()
  const offline = error?.status === 0
  return (
    <EmptyState
      icon={<IcWarn size={26} />}
      title={offline ? t('auth.offline') : t('err.title')}
      hint={
        <>
          {!offline && (error?.message || t('err.hint'))}
          {error?.requestId && (
            <>
              <br />
              <span className="mono faint" style={{ fontSize: '1.1rem' }}>
                {error.requestId}
              </span>
            </>
          )}
        </>
      }
      action={
        onRetry && (
          <Button variant="ghost" icon={<IcRefresh size={15} />} onClick={onRetry}>
            {t('auth.retry')}
          </Button>
        )
      }
    />
  )
}

/**
 * @param {{data:any, error:any, loading:boolean, reload:Function}} props
 * @param {(data:any) => JSX.Element} props.children
 */
export function Async({ query, data, error, loading, reload, children, skeleton, empty }) {
  /* Two shapes, because both are reached for and only one used to work.
     `<Async data={...} error={...}>{(d) => …}</Async>` is the original.
     `<Async query={q}>…</Async>` is what everyone writes when they already
     have the query object — and it silently rendered NOTHING, because `data`
     was undefined and the third line below returns null for that. Two
     finished features shipped blank that way.

     A component whose misuse renders an empty page rather than an error is a
     component that will be misused again, so it now accepts both. */
  const state = query ?? { data, error, loading, reload }

  // an error with nothing to fall back on is the only case that takes over
  if (state.error && !state.data) return <ErrorState error={state.error} onRetry={state.reload} />
  if (!state.data && state.loading) return skeleton ?? <Skeleton />
  if (!state.data) return empty ?? null

  const body = typeof children === 'function' ? children(state.data) : children
  // a refetch over existing data dims rather than replaces
  return state.loading ? (
    <div className="is-refetching" aria-busy="true">
      {body}
    </div>
  ) : (
    body
  )
}
