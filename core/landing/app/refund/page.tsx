// /refund route → /#contact yönlendirmesi (pilot/PoC modu, ödeme yok)
import { redirect } from "next/navigation";

export default function Page() {
  redirect("/#contact");
}
