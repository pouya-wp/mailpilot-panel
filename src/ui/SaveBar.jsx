/* ============================================================
   SAVE BAR — the answer to "did that save?"

   Every settings screen in this panel used to save silently, or on
   navigation, or not at all, and none of them ever said which. The
   reader was left to change a field and hope.

   So this shows all four states a change can be in, and they are
   genuinely different questions:

     idle    nothing to save
     dirty   you changed something and it is NOT saved yet
     saving  in flight
     saved   landed, with the time it landed

   `dirty` is the one that matters. A save button that is always
   enabled tells you nothing; one that lights up only when there is
   something to save turns the button itself into the status.

   It sticks to the bottom of its container so it stays reachable on
   a long form without following the reader up a short one.
   ============================================================ */
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { Button } from './index'
import { IcCheckC, IcWarn } from '../components/NavIcons'

/**
 * @param {boolean}  dirty     there are unsaved changes
 * @param {boolean}  saving    a save is in flight
 * @param {number}   savedAt   epoch ms of the last successful save, or 0
 * @param {string}   error     message from the last failed save, if any
 * @param {Function} onSave
 */
export function SaveBar({ dirty, saving, savedAt = 0, error = '', onSave, label }) {
  const { t } = useI18n()

  /* "Saved" should fade back to nothing after a while — a tick that never
     leaves stops meaning "just now" and starts meaning "at some point". */
  const [fresh, setFresh] = useState(false)
  useEffect(() => {
    if (!savedAt) return
    setFresh(true)
    const timer = setTimeout(() => setFresh(false), 6000)
    return () => clearTimeout(timer)
  }, [savedAt])

  return (
    <div className={`savebar${dirty ? ' savebar--dirty' : ''}`}>
      <span className="savebar__status">
        {error ? (
          <span className="savebar__error">
            <IcWarn size={14} /> {error}
          </span>
        ) : saving ? (
          <>
            <span className="savebar__spin" /> {t('save.saving')}
          </>
        ) : dirty ? (
          <span className="savebar__dirty">{t('save.unsaved')}</span>
        ) : fresh ? (
          <span className="savebar__done">
            <IcCheckC size={14} /> {t('save.saved')}
          </span>
        ) : null}
      </span>

      <Button variant="primary" loading={saving} disabled={!dirty || saving} onClick={onSave}>
        {label || t('g.save')}
      </Button>
    </div>
  )
}

/**
 * Track a form against the values it was loaded with.
 *
 * Comparison is a JSON round-trip rather than a reference check: the forms here
 * are small, flat and rebuilt on every keystroke, so identity says nothing and
 * "is this actually different from what the server has" is the real question.
 * It also means typing a change and undoing it leaves the form clean, which a
 * reference check would get wrong.
 */
export function useDirty(value) {
  const baseline = useRef(JSON.stringify(value ?? null))
  const [savedAt, setSavedAt] = useState(0)

  const current = JSON.stringify(value ?? null)
  const dirty = current !== baseline.current

  return {
    dirty,
    savedAt,
    /** Call after a successful save: the current values become the new baseline. */
    commit: () => {
      baseline.current = JSON.stringify(value ?? null)
      setSavedAt(Date.now())
    },
    /** Call when fresh values arrive from the server. */
    rebase: (next) => {
      baseline.current = JSON.stringify(next ?? null)
    },
  }
}
