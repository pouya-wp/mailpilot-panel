/* One broken page must not blank the whole panel.

   Without a boundary, a render error anywhere unmounts the entire React tree —
   the reader loses the sidebar, the top bar and any way to navigate away from
   the page that failed. Catching per page keeps the shell alive, so the worst
   case is one card saying so while everything else still works. */

import { Component } from 'react'
import { Button, EmptyState } from './index'
import { IcRefresh, IcWarn } from '../components/NavIcons'

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[page crashed]', error, info?.componentStack)
  }

  componentDidUpdate(prev) {
    // a navigation is a fresh start: clear the error when the key changes
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null })
    }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="page">
        <EmptyState
          icon={<IcWarn size={26} />}
          title={this.props.title || 'This page hit an error'}
          hint={this.state.error.message}
          action={
            <Button variant="ghost" icon={<IcRefresh size={15} />} onClick={() => window.location.reload()}>
              {this.props.retryLabel || 'Reload'}
            </Button>
          }
        />
      </div>
    )
  }
}
