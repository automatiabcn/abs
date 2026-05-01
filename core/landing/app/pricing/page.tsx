// /pricing route → /#contact yönlendirmesi (pricing sayfası kaldırıldı)
import { redirect } from "next/navigation";

export default function Page() {
  redirect("/#contact");
}
