/* ============================================================
   The navigation map.

   This used to be twenty-one destinations in six groups. It is
   now five, flat, and that is the point of the product rather
   than a tidy-up: everything that was a screen the operator had
   to visit — compose, templates, journeys, experiments, the agent
   roster — was work the agent should be doing. A person selling
   this does not want a control surface. They want to say what
   they want and see what happened.

   What survives is what a human genuinely holds an opinion about:
   what went out, who it went to, what came back, and the settings.

   Two things filter this list at render time:
     * `modules` — what this deployment was sold (see api/config).
     * nothing else. There is no per-role nav; a viewer sees the
       same map and is refused at the endpoint.

   `setup` is deliberately absent. It belongs to the implementer,
   not the customer, and is reached by URL.
   ============================================================ */
import { IcCampaign, IcChart, IcContacts, IcDashboard, IcBook, IcGear, IcInbox, IcTemplate } from '../components/NavIcons'

/* One flat list. Groups were a way of coping with twenty-one items; five do not
   need to be sorted into anything. */
export const NAV = [
  { id: 'home', labelKey: 'nav.home', icon: IcDashboard, module: null },
  { id: 'campaigns', labelKey: 'nav.campaigns', icon: IcCampaign, module: 'campaigns' },
  { id: 'audience', labelKey: 'nav.audience', icon: IcContacts, module: 'audience' },
  { id: 'designer', labelKey: 'nav.designer', icon: IcTemplate, module: 'templates' },
  { id: 'inbox', labelKey: 'nav.inbox', icon: IcInbox, module: 'inbox' },
  { id: 'insights', labelKey: 'nav.insights', icon: IcChart, module: 'insights' },
  { id: 'guide', labelKey: 'nav.guide', icon: IcBook, module: null },
  { id: 'settings', labelKey: 'nav.settings', icon: IcGear, module: null },
]

/* Every route the shell can render, including the ones with no nav entry. The
   breadcrumb and the command palette read this, so a page reachable by URL is
   still nameable. */
export const ROUTES = {
  home: { labelKey: 'nav.home', icon: IcDashboard },
  campaigns: { labelKey: 'nav.campaigns', icon: IcCampaign, module: 'campaigns' },
  audience: { labelKey: 'nav.audience', icon: IcContacts, module: 'audience' },
  designer: { labelKey: 'nav.designer', icon: IcTemplate, module: 'templates' },
  inbox: { labelKey: 'nav.inbox', icon: IcInbox, module: 'inbox' },
  insights: { labelKey: 'nav.insights', icon: IcChart, module: 'insights' },
  guide: { labelKey: 'nav.guide', icon: IcBook },
  settings: { labelKey: 'nav.settings', icon: IcGear },
  setup: { labelKey: 'setup.title', icon: IcGear },
}

export const NAV_FLAT = NAV

/** The rail's items for THIS deployment. */
export function navFor(has) {
  return NAV.filter((item) => !item.module || has(item.module))
}

export function navItem(path) {
  return ROUTES[path] || ROUTES.home
}
