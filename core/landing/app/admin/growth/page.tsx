// `/admin/growth` canonical route — re-exports the /panel/growth client
// component (Caddy 308s /panel → /admin, so the canonical surface is /admin/*).
export { default } from "@/app/panel/growth/page";
