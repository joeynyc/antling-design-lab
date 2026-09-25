# Visual plan

Purpose: a real, responsive landing page for Joey Rodriguez's practical local AI work, plus a small on-page breakdown of the source image into reusable layers.

Primary journey: arrive on the page, understand Joey's focus, scroll to the actual build, inspect model layers, and open AntLing Design Lab locally.

Reference: the 2048×2048 studio photograph generated in AntLing Design Lab, job `0e0299c587d4408185cd911cd9b6909f`. Its navy wall fills the left/top; wooden desk, compact PC, and violet monitor occupy the lower right. No visual reference contains page text. Copy and controls must be HTML.

Layout: a compact top nav above a tall immersive hero. On desktop, place the image against a matching navy field at the right/bottom and overlay live text on the naturally empty left wall. On narrow screens, stack text before the full photo. Follow with one case-study section, an interactive layer inspection section, and a footer.

Hierarchy: restrained white headline on navy, violet used as an accent, body copy at readable contrast, a single filled primary CTA. Keep page chrome quieter than the generated visual.

Asset gate: original photo accepted as the hero background. Layer assets resolved from targeted 1024px split `1aff5074a9a94be78210b168d48b021d`: accepted monitor crop `asset_00`, computer crop `asset_01`, and desk crop `asset_03`; refined wall crop from `asset_04` to exclude a residual shadow; omitted ghost-monitor crop `asset_02` because it is a model artifact. No image-generated wording or fabricated UI is used. The first split (`0f80c8554f3f4807bbf615b58af7d91f`) hallucinated text and joined desk/computer.

Behavior: anchor navigation, local Lab link, keyboard-operable layer selection, responsive layout, reduced-motion handling. No fictional contact link, project claims, or server-backed state.
