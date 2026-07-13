/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// FAZ B (2026-05-08) — chat-sidebar prompt library: 8 categories,
// 6 prompts each, 3 languages (TR/EN/ES). Replaces the 4-item
// hardcoded SAMPLE_PROMPTS in components/chat/index.tsx with a
// searchable, categorised drawer that customers actually use.
//
// Content generated via mcp__abs__ask_qwen32b/gptoss/kimi (free
// models), schema validated, and pasted as a TS array literal.
// Adding new categories: push to PROMPT_CATEGORIES + add 6 items
// to PROMPTS with category id matching, then update the test's
// integrity assertion.

import {
  Briefcase,
  Send,
  MessageCircle,
  Code,
  FileText,
  Calculator,
  BarChart,
  Sparkles,
} from "lucide-react";

export type PromptLang = "en" | "tr" | "es";

export const CATEGORY_ICONS = {
  Briefcase,
  Send,
  MessageCircle,
  Code,
  FileText,
  Calculator,
  BarChart,
  Sparkles,
} as const;

export type CategoryIconName = keyof typeof CATEGORY_ICONS;

export type PromptCategory = {
  id: string;
  iconName: CategoryIconName;
  title: Record<PromptLang, string>;
  description: Record<PromptLang, string>;
};

export type PromptItem = {
  id: string;
  category: string;
  title: Record<PromptLang, string>;
  description: Record<PromptLang, string>;
  prompt: Record<PromptLang, string>;
  placeholders: string[];
  estTokens: number;
};

export const PROMPT_CATEGORIES: PromptCategory[] = [
  {
    id: "founder",
    iconName: "Sparkles",
    title: {
      en: "Solo founder",
      tr: "Kurucu",
      es: "Fundador",
    },
    description: {
      en: "Operations and growth for indie hackers and one-person shops.",
      tr: "Indie hacker ve tek kişilik ekipler için operasyon ve büyüme.",
      es: "Operaciones y crecimiento para indie hackers y equipos unipersonales.",
    },
  },
  {
    id: "agency",
    iconName: "Briefcase",
    title: {
      en: "Agency / Consulting",
      tr: "Ajans / Danışmanlık",
      es: "Agencia / Consultoría",
    },
    description: {
      en: "Proposals, SOWs, status reports and case studies for client work.",
      tr: "Müşteri işleri için teklif, SOW, durum raporu ve vaka çalışmaları.",
      es: "Propuestas, SOW, informes de estado y casos de estudio para clientes.",
    },
  },
  {
    id: "sales",
    iconName: "Send",
    title: {
      en: "Sales & BD",
      tr: "Satış ve İş Geliştirme",
      es: "Ventas y Desarrollo",
    },
    description: {
      en: "Outreach, follow-ups, demos and objection handling that close deals.",
      tr: "Anlaşmaları kapatan dış arama, takip, demo ve itiraz yönetimi.",
      es: "Prospección, seguimientos, demos y manejo de objeciones que cierran tratos.",
    },
  },
  {
    id: "support",
    iconName: "MessageCircle",
    title: {
      en: "Customer Support & Ops",
      tr: "Müşteri Destek ve Operasyon",
      es: "Soporte y Operaciones",
    },
    description: {
      en: "Ticket triage, refunds, SLA breaches and FAQ entries.",
      tr: "Talep triajı, iade, SLA ihlali ve SSS girişleri.",
      es: "Triaje de tickets, reembolsos, incumplimientos de SLA y FAQ.",
    },
  },
  {
    id: "developer",
    iconName: "Code",
    title: {
      en: "Developer / Engineering",
      tr: "Yazılım ve Mühendislik",
      es: "Desarrollador / Ingeniería",
    },
    description: {
      en: "Code review, ADRs, PR descriptions and tech-debt audits.",
      tr: "Kod incelemesi, ADR, PR açıklaması ve teknik borç denetimi.",
      es: "Revisión de código, ADRs, descripciones de PR y auditoría de deuda técnica.",
    },
  },
  {
    id: "content",
    iconName: "FileText",
    title: {
      en: "Content & Marketing",
      tr: "İçerik ve Pazarlama",
      es: "Contenido y Marketing",
    },
    description: {
      en: "Blog outlines, social posts, newsletters and press releases.",
      tr: "Blog taslakları, sosyal medya gönderileri, bültenler ve basın bültenleri.",
      es: "Esquemas de blog, publicaciones sociales, boletines y comunicados de prensa.",
    },
  },
  {
    id: "finance",
    iconName: "Calculator",
    title: {
      en: "Finance, Legal, Admin",
      tr: "Finans, Hukuk, İdare",
      es: "Finanzas, Legal, Admin",
    },
    description: {
      en: "Invoices, contracts, GDPR addenda and compliance checks.",
      tr: "Faturalar, sözleşmeler, KVKK ekleri ve uyumluluk kontrolleri.",
      es: "Facturas, contratos, anexos GDPR y verificaciones de cumplimiento.",
    },
  },
  {
    id: "data",
    iconName: "BarChart",
    title: {
      en: "Data & Research",
      tr: "Veri ve Araştırma",
      es: "Datos e Investigación",
    },
    description: {
      en: "Surveys, interview guides, A/B tests and segmentation.",
      tr: "Anket, görüşme rehberi, A/B test ve segmentasyon.",
      es: "Encuestas, guías de entrevista, pruebas A/B y segmentación.",
    },
  },
];

export const PROMPTS: PromptItem[] = [
  {
    id: "founder-weekly-review",
    category: "founder",
    title: {
      en: "Weekly Founder Review",
      tr: "Haftalık Kurucu İncelemesi",
      es: "Revisión Semanal del Fundador",
    },
    description: {
      en: "Summarize the past seven days, noting highlights, lowlights, and next steps.",
      tr: "Geçtiğimiz yedi günü özetleyin, öne çıkanları, eksikleri ve sonraki adımları belirtin.",
      es: "Resume los últimos siete días, señalando los aspectos positivos, negativos y los próximos pasos.",
    },
    prompt: {
      en: "Write a concise weekly review for {founder} covering the period {date_range}. Include three bullet points for highlights, three for lowlights, and a short list of actionable next steps. Keep the tone professional and forward-looking.",
      tr: "{founder} için {date_range} dönemini kapsayan kısa bir haftalık değerlendirme yazın. Öne çıkanlar için üç madde, eksikler için üç madde ve uygulanabilir sonraki adımların kısa bir listesini ekleyin. Tonu profesyonel ve ileriye dönük tutun.",
      es: "Redacta una revisión semanal concisa para {founder} del rango {date_range}. Añade tres viñetas de aspectos destacados, tres de aspectos negativos y una lista breve de pasos siguientes. Usa un tono profesional y proactivo.",
    },
    placeholders: ["{founder}", "{date_range}"],
    estTokens: 110,
  },
  {
    id: "founder-customer-email",
    category: "founder",
    title: {
      en: "Reengagement Email to Churned Customer",
      tr: "Müşteri Yeniden Katılım E-postası",
      es: "Correo de Reenganche al Cliente",
    },
    description: {
      en: "Craft a thoughtful email aiming to understand reasons for churn and invite return.",
      tr: "Müşteri kaybı nedenlerini anlamayı ve geri dönüşe davet etmeyi hedefleyen düşünceli bir e-posta hazırlayın.",
      es: "Redacta un correo considerado para entender la causa del abandono e invitar al regreso.",
    },
    prompt: {
      en: "Compose an email from {founder} of {company} to a churned {audience}. Acknowledge their experience, ask for feedback on {topic}, and propose a personalized incentive to return. Use a friendly yet respectful tone.",
      tr: "{company} kurucusu {founder} adına, hizmeti bırakan bir {audience} için e-posta yazın. Deneyimlerini takdir edin, {topic} hakkında geri bildirim isteyin ve geri dönmesi için kişiselleştirilmiş bir teşvik önerin. Samimi ama saygılı bir ton kullanın.",
      es: "Escribe un correo de {founder} de {company} para un {audience} que canceló. Reconoce su experiencia, pide retroalimentación sobre {topic} y sugiere un incentivo personalizado para regresar. Mantén un tono amistoso y respetuoso.",
    },
    placeholders: ["{founder}", "{company}", "{audience}", "{topic}"],
    estTokens: 130,
  },
  {
    id: "founder-feature-priority",
    category: "founder",
    title: {
      en: "Feature Request ICE Prioritization",
      tr: "Özellik İsteği ICE Önceliklendirme",
      es: "Priorización ICE de Solicitudes",
    },
    description: {
      en: "Rank incoming feature requests using Impact, Confidence, and Ease scores to decide development order.",
      tr: "Önceliklendirme için gelen özellik isteklerini Etki, Güven ve Kolaylık puanlarıyla sıralayın.",
      es: "Ordena las solicitudes de funciones usando puntuaciones de Impacto, Confianza y Facilidad para decidir el orden de desarrollo.",
    },
    prompt: {
      en: "List the feature requests for {company} and assign an Impact, Confidence, and Ease score (1-10) to each. Calculate the ICE total and sort the list from highest to lowest. Provide a brief justification for the top three priorities.",
      tr: "{company} için gelen özellik isteklerini listeleyin ve her birine Etki, Güven ve Kolaylık puanı (1-10) atayın. Toplam ICE değerini hesaplayın ve listeyi en yüksekten en düşüğe sıralayın. İlk üç öncelik için kısa bir gerekçe sunun.",
      es: "Lista las peticiones de funcionalidades de {company} y asigna una puntuación de Impacto, Confianza y Facilidad (1-10) a cada una. Calcula el total ICE y ordena de mayor a menor. Proporciona una breve justificación para las tres prioridades superiores.",
    },
    placeholders: ["{company}"],
    estTokens: 120,
  },
  {
    id: "founder-pricing-reflection",
    category: "founder",
    title: {
      en: "Pricing Tier Reflection & Experiment",
      tr: "Fiyatlandırma Katmanı Değerlendirmesi",
      es: "Reflexión de Precio y Experimento",
    },
    description: {
      en: "Analyze the current pricing tier of the company and suggest a single experiment to test a new price point.",
      tr: "Şirketin mevcut fiyatlandırma katmanını analiz edin ve yeni bir fiyat noktası test etmek için tek bir deney önerin.",
      es: "Examina el nivel de precios actual de la empresa y propone un experimento para probar un nuevo punto de precio.",
    },
    prompt: {
      en: "Review the pricing tier structure of {company} for the last {date_range}. Identify any gaps in value perception versus price. Propose one A/B test that changes the price or feature bundle, stating the hypothesis and success metric.",
      tr: "{company} şirketinin son {date_range} dönemindeki fiyatlandırma katmanı yapısını gözden geçirin. Değer algısı ile fiyat arasındaki boşlukları belirleyin. Fiyatı veya özellik paketini değiştiren tek bir A/B testi önerin; hipotezi ve başarı metriğini açıkça belirtin.",
      es: "Analiza la estructura de precios de {company} en el último {date_range}. Detecta brechas entre la percepción de valor y el precio. Sugiere una prueba A/B que altere el precio o el conjunto de características, especificando la hipótesis y la métrica de éxito.",
    },
    placeholders: ["{company}", "{date_range}"],
    estTokens: 130,
  },
  {
    id: "founder-competitor-scan",
    category: "founder",
    title: {
      en: "5-Minute Competitor Scan",
      tr: "5 Dakikalık Rakip Analizi",
      es: "Resumen Rápido de Competidor",
    },
    description: {
      en: "Provide a concise five-minute summary of the latest moves by a key competitor.",
      tr: "Önemli bir rakibin son hamleleri hakkında kısa, beş dakikalık bir özet sunun.",
      es: "Entrega un resumen breve de cinco minutos sobre las últimas acciones de un competidor importante.",
    },
    prompt: {
      en: "Identify the top competitor of {company} in the {topic} market. Summarize their recent product launches, pricing changes, and marketing campaigns in bullet points. Highlight one opportunity or threat for {company}.",
      tr: "{topic} pazarındaki {company} şirketinin başlıca rakibini belirleyin. Son ürün lansmanlarını, fiyat değişikliklerini ve pazarlama kampanyalarını madde madde özetleyin. {company} için bir fırsat veya tehdidi öne çıkarın.",
      es: "Detecta al competidor principal de {company} en el sector de {topic}. Resume sus últimos lanzamientos, variaciones de precios y campañas de marketing en puntos breves. Resalta una oportunidad o amenaza para {company}.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 110,
  },
  {
    id: "founder-investor-update",
    category: "founder",
    title: {
      en: "Monthly Investor Update",
      tr: "Aylık Yatırımcı Güncellemesi",
      es: "Actualización Mensual para Inversores",
    },
    description: {
      en: "Create a concise monthly update for investors covering MRR, burn rate, and current asks.",
      tr: "MRR, yakım hızı ve mevcut talepleri kapsayan kısa bir aylık yatırımcı güncellemesi oluşturun.",
      es: "Prepara una actualización mensual concisa para inversores que incluya MRR, tasa de consumo y peticiones actuales.",
    },
    prompt: {
      en: "Draft a one-page investor update for {founder} of {company}. Include sections for MRR growth, current burn rate, runway, and a clear ask (e.g., introductions, funding, advice). Keep the tone transparent and forward-focused.",
      tr: "{company} kurucusu {founder} için tek sayfalık bir yatırımcı güncellemesi taslağı hazırlayın. MRR büyümesi, mevcut yakım hızı, runway ve net bir talep (örneğin tanıştırma, yatırım, tavsiye) bölümlerini ekleyin. Tonu şeffaf ve geleceğe odaklı tutun.",
      es: "Escribe una actualización de una página para inversores de {founder} de {company}. Incluye secciones de crecimiento de MRR, tasa de consumo actual, runway y una petición clara (por ejemplo, contactos, financiación, asesoría). Usa un tono transparente y con visión de futuro.",
    },
    placeholders: ["{founder}", "{company}"],
    estTokens: 150,
  },
  {
    id: "agency-client-proposal",
    category: "agency",
    title: {
      en: "Draft Client Proposal",
      tr: "Müşteri Teklifi Taslağı",
      es: "Borrador Propuesta Cliente",
    },
    description: {
      en: "Generate a concise one-page client proposal outlining the project scope, pricing, and timeline.",
      tr: "Proje kapsamını, fiyatlandırmayı ve zaman çizelgesini özetleyen kısa bir sayfalık müşteri teklifi oluşturun.",
      es: "Genere una propuesta de cliente concisa de una página que describa el alcance del proyecto, el precio y el cronograma.",
    },
    prompt: {
      en: "Draft a one-page client proposal for {company} regarding {topic}. Include a clear project scope, detailed pricing for {amount}, and a realistic timeline for {date_range}. The tone should be {tone}.",
      tr: "{company} için {topic} hakkında tek sayfalık bir müşteri teklifi taslağı hazırlayın. Net bir proje kapsamı, {amount} için ayrıntılı fiyatlandırma ve {date_range} için gerçekçi bir zaman çizelgesi ekleyin. Ton {tone} olmalı.",
      es: "Redacte una propuesta de cliente de una página para {company} sobre {topic}. Incluya un alcance de proyecto claro, precios detallados para {amount} y un cronograma realista para {date_range}. El tono debe ser {tone}.",
    },
    placeholders: ["{company}", "{topic}", "{amount}", "{date_range}", "{tone}"],
    estTokens: 150,
  },
  {
    id: "agency-sow-draft",
    category: "agency",
    title: {
      en: "Statement of Work Draft",
      tr: "İş Tanımı Taslağı",
      es: "Borrador Declaración Trabajo",
    },
    description: {
      en: "Create a comprehensive Statement of Work detailing deliverables, milestones, and a payment schedule.",
      tr: "Teslimatları, kilometre taşlarını ve ödeme planını detaylandıran kapsamlı bir İş Tanımı oluşturun.",
      es: "Cree una Declaración de Trabajo completa que detalle los entregables, los hitos y un cronograma de pagos.",
    },
    prompt: {
      en: "Draft a Statement of Work (SOW) for the {topic} project with {company}. Outline specific deliverables, key milestones with target dates, and a clear payment schedule for {amount} over {date_range}. Specify the responsibilities of both parties.",
      tr: "{company} ile {topic} projesi için bir İş Tanımı (SOW) taslağı hazırlayın. Belirli teslimatları, hedef tarihlerle ana kilometre taşlarını ve {date_range} boyunca {amount} için net bir ödeme planını özetleyin. Her iki tarafın sorumluluklarını belirtin.",
      es: "Redacte una Declaración de Trabajo (SOW) para el proyecto {topic} con {company}. Describa los entregables específicos, los hitos clave con fechas objetivo y un cronograma de pagos claro para {amount} durante {date_range}. Especifique las responsabilidades de ambas partes.",
    },
    placeholders: ["{topic}", "{company}", "{amount}", "{date_range}"],
    estTokens: 160,
  },
  {
    id: "agency-project-status",
    category: "agency",
    title: {
      en: "Weekly Project Status",
      tr: "Haftalık Proje Durumu",
      es: "Estado Semanal Proyecto",
    },
    description: {
      en: "Generate a weekly project status update for the client, including RAG status for key areas.",
      tr: "Müşteri için ana alanlar için RAG (Kırmızı, Sarı, Yeşil) durumu dahil haftalık bir proje durumu güncellemesi oluşturun.",
      es: "Genere una actualización semanal del estado del proyecto para el cliente, incluyendo el estado RAG para las áreas clave.",
    },
    prompt: {
      en: "Prepare a weekly project status update for {company} regarding {topic}. Include RAG status for scope, budget, and timeline. Briefly describe progress, any blockers, and next steps for {date_range}, and address {audience} as the primary reader.",
      tr: "{company} için {topic} hakkında haftalık bir proje durumu güncellemesi hazırlayın. Kapsam, bütçe ve takvim için RAG durumunu ekleyin. {date_range} dönemi için ilerlemeyi, engelleri ve sonraki adımları kısaca açıklayın; birincil okuyucu olarak {audience} kitlesine hitap edin.",
      es: "Prepare una actualización semanal del estado del proyecto para {company} sobre {topic}. Incluya el estado RAG para alcance, presupuesto y cronograma. Describa brevemente el progreso, cualquier obstáculo y los próximos pasos para {date_range}, dirigiéndose a {audience} como lector principal.",
    },
    placeholders: ["{company}", "{topic}", "{date_range}", "{audience}"],
    estTokens: 170,
  },
  {
    id: "agency-case-study",
    category: "agency",
    title: {
      en: "Case Study Skeleton",
      tr: "Vaka Çalışması Taslağı",
      es: "Esqueleto Caso Estudio",
    },
    description: {
      en: "Outline a case study skeleton from a recently finished project, highlighting challenges, solutions, and results.",
      tr: "Yakın zamanda tamamlanmış bir projeden zorlukları, çözümleri ve sonuçları vurgulayan bir vaka çalışması taslağı oluşturun.",
      es: "Esquematice un esqueleto de caso de estudio de un proyecto recientemente terminado, destacando desafíos, soluciones y resultados.",
    },
    prompt: {
      en: "Generate a case study skeleton for the {topic} project completed for {company}. Include sections for the initial challenge, the proposed solution, implementation details, and measurable results aligned with {goal}. The target audience is {audience}.",
      tr: "{company} için tamamlanan {topic} projesi için bir vaka çalışması taslağı oluşturun. Başlangıçtaki zorluk, önerilen çözüm, uygulama detayları ve {goal} ile uyumlu ölçülebilir sonuçlar için bölümler ekleyin. Hedef kitle {audience}.",
      es: "Genere un esqueleto de caso de estudio para el proyecto {topic} completado para {company}. Incluya secciones para el desafío inicial, la solución propuesta, los detalles de implementación y los resultados medibles alineados con {goal}. La audiencia objetivo es {audience}.",
    },
    placeholders: ["{topic}", "{company}", "{goal}", "{audience}"],
    estTokens: 140,
  },
  {
    id: "agency-discovery-call",
    category: "agency",
    title: {
      en: "Discovery Call Agenda",
      tr: "Keşif Görüşmesi Gündemi",
      es: "Agenda Llamada Descubrimiento",
    },
    description: {
      en: "Create a 30-minute discovery call agenda with key questions to understand a potential client's needs.",
      tr: "Potansiyel bir müşterinin ihtiyaçlarını anlamak için temel sorular içeren 30 dakikalık bir keşif görüşmesi gündemi oluşturun.",
      es: "Cree una agenda de llamada de descubrimiento de 30 minutos con preguntas clave para comprender las necesidades de un cliente potencial.",
    },
    prompt: {
      en: "Draft a 30-minute discovery call agenda for a meeting with {company} about {topic}. Include an introduction, key questions to uncover their challenges and {goal}, and a clear next steps section. Keep the tone {tone} and tailor it for {audience}.",
      tr: "{topic} hakkında {company} ile yapılacak bir toplantı için 30 dakikalık bir keşif görüşmesi gündemi hazırlayın. Bir giriş, zorluklarını ve {goal} hedefini ortaya çıkarmak için temel sorular ve net bir sonraki adımlar bölümü ekleyin. Tonu {tone} tutun ve {audience} için uyarlayın.",
      es: "Redacte una agenda de llamada de descubrimiento de 30 minutos para una reunión con {company} sobre {topic}. Incluya una introducción, preguntas clave para descubrir sus desafíos y {goal}, y una sección clara de próximos pasos. Mantenga el tono {tone} y adáptelo a {audience}.",
    },
    placeholders: ["{company}", "{topic}", "{goal}", "{tone}", "{audience}"],
    estTokens: 150,
  },
  {
    id: "agency-contract-review",
    category: "agency",
    title: {
      en: "Vendor Contract Review",
      tr: "Tedarikçi Sözleşme İncelemesi",
      es: "Revisión Contrato Proveedor",
    },
    description: {
      en: "Highlight potentially risky clauses and areas of concern in a vendor contract.",
      tr: "Bir tedarikçi sözleşmesindeki potansiyel riskli maddeleri ve endişe alanlarını vurgulayın.",
      es: "Resalte cláusulas potencialmente riesgosas y áreas de preocupación en un contrato de proveedor.",
    },
    prompt: {
      en: "Review the vendor contract from {company} regarding {topic} and identify any clauses that could pose a risk. Specifically, look for issues related to liability, payment terms for {amount}, and termination clauses. Summarize the potential impact for {audience} and suggest mitigation strategies aligned with {goal}.",
      tr: "{company} firmasının {topic} hakkındaki tedarikçi sözleşmesini inceleyin ve risk oluşturabilecek maddeleri belirleyin. Özellikle sorumluluk, {amount} için ödeme koşulları ve fesih maddeleriyle ilgili sorunları arayın. Potansiyel etkiyi {audience} için özetleyin ve {goal} ile uyumlu hafifletme stratejileri önerin.",
      es: "Revise el contrato de proveedor de {company} sobre {topic} e identifique cualquier cláusula que pueda representar un riesgo. Específicamente, busque problemas relacionados con la responsabilidad, los términos de pago para {amount} y las cláusulas de terminación. Resuma el impacto potencial para {audience} y sugiera estrategias de mitigación alineadas con {goal}.",
    },
    placeholders: ["{company}", "{topic}", "{amount}", "{audience}", "{goal}"],
    estTokens: 180,
  },
  {
    id: "sales-cold-outreach",
    category: "sales",
    title: {
      en: "Cold Email Outreach",
      tr: "Soğuk E-posta Gönderimi",
      es: "Correo Frío de Ventas",
    },
    description: {
      en: "Write a concise cold email that captures attention and drives a single specific action.",
      tr: "Dikkat çeken ve tek bir eyleme yönlendiren öz bir soğuk e-posta yazın.",
      es: "Redacta un correo frío conciso que capte la atención y genere una acción específica.",
    },
    prompt: {
      en: "Draft a personalized email to {audience} at {company} highlighting how we solve {topic}. Include a clear CTA to {goal} and keep the tone {tone}. End with a question to encourage a reply.",
      tr: "{company} şirketindeki {audience} için {topic} konusunda nasıl çözüm sunduğumuzu vurgulayan kişiselleştirilmiş bir e-posta taslak hazırlayın. {goal} hedefi için net bir eylem çağrısı ekleyin ve tonu {tone} tutun. Yanıt almak için soruyla bitirin.",
      es: "Redacta un correo personalizado para {audience} en {company} destacando cómo resolvemos {topic}. Incluye una CTA clara para {goal} y mantén el tono {tone}. Termina con una pregunta para fomentar respuesta.",
    },
    placeholders: ["{audience}", "{company}", "{topic}", "{goal}", "{tone}"],
    estTokens: 120,
  },
  {
    id: "sales-discovery-agenda",
    category: "sales",
    title: {
      en: "Discovery Meeting Agenda",
      tr: "Keşif Görüşmesi Gündemi",
      es: "Agenda de Reunión de Descubrimiento",
    },
    description: {
      en: "Structure a 45-minute agenda to uncover pain points and qualify the opportunity.",
      tr: "Ağrı noktalarını ortaya çıkarmak ve fırsatı nitelendirmek için 45 dakikalık bir gündem yapılandırın.",
      es: "Estructura una agenda de 45 minutos para descubrir dolores y calificar la oportunidad.",
    },
    prompt: {
      en: "Create a timed agenda for a discovery call with {audience} at {company}. Cover current challenges around {topic}, desired outcomes, and decision process. Allocate time for each section to stay within 45 minutes and set {goal} for next steps.",
      tr: "{company} şirketindeki {audience} ile yapılacak keşif görüşmesi için zamanlanmış bir gündem oluşturun. {topic} konusundaki mevcut zorlukları, istenen sonuçları ve karar sürecini ele alın. Her bölüm için 45 dakikada kalacak şekilde zaman ayırın ve sonraki adımlar için {goal} belirleyin.",
      es: "Crea una agenda cronometrada para una llamada de descubrimiento con {audience} en {company}. Cubre desafíos actuales sobre {topic}, resultados deseados y proceso de decisión. Asigna tiempo para cada sección para mantener 45 minutos y establece {goal} para siguientes pasos.",
    },
    placeholders: ["{audience}", "{company}", "{topic}", "{goal}"],
    estTokens: 135,
  },
  {
    id: "sales-objection-handling",
    category: "sales",
    title: {
      en: "Price Objection Response",
      tr: "Fiyat İtirazı Yanıtı",
      es: "Respuesta a Objeción de Precio",
    },
    description: {
      en: "Compose a diplomatic reply that reframes value and justifies the investment clearly.",
      tr: "Değeri yeniden çerçeveleyen ve yatırımı açıkça haklı çıkaran diplomatik bir yanıt yazın.",
      es: "Redacta una respuesta diplomática que reformule el valor y justifique la inversión claramente.",
    },
    prompt: {
      en: "Respond to a prospect saying we are too expensive compared to {tier} alternatives. Acknowledge their concern, pivot to ROI around {topic}, and offer a payment plan for {amount} if needed. Keep the tone {tone} and aim to {goal}.",
      tr: "{tier} alternatiflerine kıyasla çok pahalı olduğumuzu söyleyen bir potansiyel müşteriye yanıt verin. Endişelerini kabul edin, {topic} konusunda ROI'ye odaklanın ve gerekirse {amount} için ödeme planı teklif edin. Tonu {tone} tutun ve {goal} hedefleyin.",
      es: "Responde a un prospecto que dice que somos demasiado caros comparado con alternativas {tier}. Reconoce su preocupación, pivota hacia el ROI en {topic}, y ofrece un plan de pago para {amount} si es necesario. Mantén el tono {tone} y apunta a {goal}.",
    },
    placeholders: ["{tier}", "{topic}", "{amount}", "{tone}", "{goal}"],
    estTokens: 145,
  },
  {
    id: "sales-followup",
    category: "sales",
    title: {
      en: "Polite No-Response Follow-Up",
      tr: "Yanıtsız Kalanlara Nazik Takip",
      es: "Seguimiento Cortés sin Respuesta",
    },
    description: {
      en: "Craft a respectful follow-up email that reignites interest without sounding desperate or pushy.",
      tr: "Çaresiz veya ısrarcı görünmeden ilgiyi yeniden alevlendiren saygılı bir takip e-postası hazırlayın.",
      es: "Crea un correo de seguimiento respetuoso que reavive el interés sin sonar desesperado.",
    },
    prompt: {
      en: "Write a brief follow-up to {audience} at {company} who went silent after our last conversation about {topic}. Reference a recent {channel} update or insight, suggest a specific {date_range} to reconnect, and keep the tone {tone}.",
      tr: "{topic} hakkındaki son görüşmemizden sonra sessiz kalan {company} şirketindeki {audience} için kısa bir takip mesajı yazın. Son bir {channel} güncellemesine veya içgörüsüne atıfta bulunun, yeniden bağlanmak için belirli bir {date_range} önerin ve tonu {tone} tutun.",
      es: "Escribe un breve seguimiento para {audience} en {company} que se quedó en silencio tras nuestra última conversación sobre {topic}. Menciona una actualización reciente de {channel} o insight, sugiere un {date_range} específico para reconectar, y mantén el tono {tone}.",
    },
    placeholders: ["{audience}", "{company}", "{topic}", "{channel}", "{date_range}", "{tone}"],
    estTokens: 130,
  },
  {
    id: "sales-demo-script",
    category: "sales",
    title: {
      en: "Product Demo Script",
      tr: "Ürün Tanıtım Metni",
      es: "Guion de Demo de Producto",
    },
    description: {
      en: "Outline a 15-minute demo script tailored to a specific buyer persona and use case.",
      tr: "Belirli bir alıcı kişisine ve kullanım senaryosuna göre uyarlanmış 15 dakikalık bir tanıtım metni oluşturun.",
      es: "Esboza un guion de demo de 15 minutos adaptado a un perfil de comprador específico.",
    },
    prompt: {
      en: "Build a 15-minute demo script for {audience} at {tier} companies focusing on {topic}. Start with a hook about {goal}, show three key features with live examples, and close with next steps to {channel} by {date_range}.",
      tr: "{topic} konusuna odaklanan {tier} şirketlerindeki {audience} için 15 dakikalık bir tanıtım metni oluşturun. {goal} hakkında bir kancayla başlayın, canlı örneklerle üç temel özelliği gösterin ve {date_range} tarihine kadar {channel} üzerinden sonraki adımlarla kapatın.",
      es: "Construye un guion de demo de 15 minutos para {audience} en empresas {tier} enfocado en {topic}. Comienza con un gancho sobre {goal}, muestra tres características clave con ejemplos en vivo, y cierra con siguientes pasos hacia {channel} para {date_range}.",
    },
    placeholders: ["{audience}", "{tier}", "{topic}", "{goal}", "{channel}", "{date_range}"],
    estTokens: 140,
  },
  {
    id: "sales-linkedin-dm",
    category: "sales",
    title: {
      en: "LinkedIn Connection Message",
      tr: "LinkedIn Bağlantı Mesajı",
      es: "Mensaje de Conexión en LinkedIn",
    },
    description: {
      en: "Write a short, authentic LinkedIn DM that sparks curiosity and avoids overt sales pitches.",
      tr: "Merak uyandıran ve açık satış konuşmasından kaçınan kısa, özgün bir LinkedIn DM'si yazın.",
      es: "Redacta un DM corto y auténtico de LinkedIn que despierte curiosidad y evite ventas directas.",
    },
    prompt: {
      en: "Draft a LinkedIn DM to {audience} at {company} mentioning a specific {topic} they posted about. Ask a thoughtful question related to {goal}, offer a quick insight about {channel} trends, and suggest a brief chat in {date_range} without pitching.",
      tr: "{company} şirketindeki {audience} için {topic} hakkında gönderi paylaştıklarına atıfta bulunan bir LinkedIn DM'si taslak hazırlayın. {goal} ile ilgili düşündürücü bir soru sorun, {channel} trendleri hakkında hızlı bir içgörü sunun ve satış yapmadan {date_range} içinde kısa bir sohbet önerin.",
      es: "Redacta un DM de LinkedIn para {audience} en {company} mencionando un {topic} específico sobre el que publicaron. Haz una pregunta reflexiva relacionada con {goal}, ofrece una idea rápida sobre tendencias de {channel}, y sugiere una breve charla en {date_range} sin vender.",
    },
    placeholders: ["{audience}", "{company}", "{topic}", "{goal}", "{channel}", "{date_range}"],
    estTokens: 135,
  },
  {
    id: "support-ticket-triage",
    category: "support",
    title: {
      en: "Classify Support Ticket",
      tr: "Destek Talebi Sınıflandırma",
      es: "Clasificar Ticket de Soporte",
    },
    description: {
      en: "Analyze the customer's request to determine its priority, appropriate owner, and service level agreement.",
      tr: "Müşterinin talebini analiz ederek önceliğini, atanacak kişiyi ve hizmet seviyesi anlaşmasını belirleyin.",
      es: "Analice la solicitud del cliente para determinar su prioridad, el propietario adecuado y el acuerdo de nivel de servicio.",
    },
    prompt: {
      en: "You are a support agent at {company}. Classify the following customer support ticket about {topic}. Determine its priority (low, medium, high, urgent), the appropriate team or agent owner, and the applicable SLA tier {tier} (e.g., 24-hour response, 4-hour resolution). The ticket content is: \"{ticket_content}\".",
      tr: "{company} şirketinde bir destek temsilcisisiniz. {topic} hakkındaki aşağıdaki müşteri destek talebini sınıflandırın. Önceliğini (düşük, orta, yüksek, acil), uygun ekip veya temsilci sahibini ve geçerli SLA katmanı {tier}'i (örn. 24 saat yanıt, 4 saat çözüm) belirleyin. Talep içeriği: \"{ticket_content}\".",
      es: "Eres un agente de soporte en {company}. Clasifica el siguiente ticket de soporte sobre {topic}. Determina su prioridad (baja, media, alta, urgente), el equipo o agente propietario adecuado y el nivel de SLA aplicable {tier} (ej. respuesta en 24 horas, resolución en 4 horas). El contenido del ticket es: \"{ticket_content}\".",
    },
    placeholders: ["{company}", "{topic}", "{tier}", "{ticket_content}"],
    estTokens: 150,
  },
  {
    id: "support-bug-report",
    category: "support",
    title: {
      en: "Rewrite Bug Report",
      tr: "Hata Raporunu Yeniden Yaz",
      es: "Reescribir Informe de Error",
    },
    description: {
      en: "Transform a customer's raw bug description into a structured, clear, and actionable engineering ticket for developers.",
      tr: "Bir müşterinin ham hata açıklamasını geliştiriciler için yapılandırılmış, net ve eyleme geçirilebilir bir mühendislik talebine dönüştürün.",
      es: "Transforme la descripción de un error de un cliente en un ticket de ingeniería estructurado, claro y procesable para desarrolladores.",
    },
    prompt: {
      en: "Rewrite the following customer bug report for {company} into a concise engineering ticket about {topic}. Include steps to reproduce, expected behavior, actual behavior, and any relevant user environment details for the {audience} engineering team. The original customer report is: \"{customer_report}\".",
      tr: "Aşağıdaki {company} müşteri hata raporunu {topic} hakkında kısa bir mühendislik talebine dönüştürün. {audience} mühendislik ekibi için yeniden üretme adımlarını, beklenen davranışı, mevcut davranışı ve ilgili kullanıcı ortamı ayrıntılarını ekleyin. Orijinal müşteri raporu: \"{customer_report}\".",
      es: "Reescribe el siguiente informe de error del cliente para {company} en un ticket de ingeniería conciso sobre {topic}. Incluye los pasos para reproducir, el comportamiento esperado, el comportamiento actual y cualquier detalle relevante del entorno del usuario para el equipo de ingeniería {audience}. El informe original del cliente es: \"{customer_report}\".",
    },
    placeholders: ["{company}", "{topic}", "{audience}", "{customer_report}"],
    estTokens: 160,
  },
  {
    id: "support-refund-response",
    category: "support",
    title: {
      en: "Empathetic Refund Response",
      tr: "Empatik İade Yanıtı",
      es: "Respuesta Empática de Reembolso",
    },
    description: {
      en: "Craft a compassionate and clear response to a customer's refund request, outlining the decision and next steps.",
      tr: "Bir müşterinin iade talebine şefkatli ve net bir yanıt oluşturun, kararı ve sonraki adımları özetleyin.",
      es: "Elabore una respuesta compasiva y clara a la solicitud de reembolso de un cliente, detallando la decisión y los próximos pasos.",
    },
    prompt: {
      en: "Write an empathetic response from {company} to a customer's refund request for {amount}. State whether the refund is approved or denied, explain the reason, and outline the next steps via {channel}. Keep the tone {tone}. The customer's request is: \"{refund_request}\".",
      tr: "{company} adına, {amount} tutarındaki bir iade talebine empatik bir yanıt yazın. İadenin onaylandığını veya reddedildiğini belirtin, nedeni açıklayın ve {channel} üzerinden sonraki adımları özetleyin. Tonu {tone} tutun. Müşterinin talebi: \"{refund_request}\".",
      es: "Escribe una respuesta empática de {company} a la solicitud de reembolso de un cliente por {amount}. Indica si el reembolso está aprobado o denegado, explica la razón y describe los próximos pasos vía {channel}. Mantén el tono {tone}. La solicitud del cliente es: \"{refund_request}\".",
    },
    placeholders: ["{company}", "{amount}", "{channel}", "{tone}", "{refund_request}"],
    estTokens: 180,
  },
  {
    id: "support-sla-breach",
    category: "support",
    title: {
      en: "SLA Breach Apology",
      tr: "SLA İhlali Özrü",
      es: "Disculpa por Incumplimiento de SLA",
    },
    description: {
      en: "Compose a sincere apology and provide a clear explanation to a customer after a service level agreement breach.",
      tr: "Hizmet seviyesi anlaşması ihlali sonrası bir müşteriye içten bir özür ve net bir açıklama yazın.",
      es: "Redacte una disculpa sincera y proporcione una explicación clara a un cliente después de un incumplimiento del acuerdo de nivel de servicio.",
    },
    prompt: {
      en: "Draft a customer-facing message from {company} acknowledging an SLA breach on {topic} during {date_range}. Apologize sincerely for the delay, briefly explain the situation without making excuses, and clearly state the steps and remedy ({amount} credit or equivalent) being taken to prevent future occurrences. Keep the tone {tone}.",
      tr: "{date_range} döneminde {topic} konusunda yaşanan bir SLA ihlalini kabul eden {company} adına müşteri odaklı bir mesaj taslağı hazırlayın. Gecikme için içtenlikle özür dileyin, mazeret üretmeden durumu kısaca açıklayın ve sorunu çözmek ve gelecekteki tekrarları önlemek için atılan adımları ve telafiyi ({amount} kredi veya eşdeğeri) açıkça belirtin. Tonu {tone} tutun.",
      es: "Redacta un mensaje de {company} dirigido al cliente reconociendo un incumplimiento del SLA en {topic} durante {date_range}. Disculpa sinceramente por el retraso, explica la situación brevemente sin poner excusas y establece claramente los pasos y la compensación ({amount} de crédito o equivalente) que se están tomando para evitar futuras ocurrencias. Mantén el tono {tone}.",
    },
    placeholders: ["{company}", "{topic}", "{date_range}", "{amount}", "{tone}"],
    estTokens: 190,
  },
  {
    id: "support-faq-entry",
    category: "support",
    title: {
      en: "Create FAQ Entry",
      tr: "SSS Girişi Oluştur",
      es: "Crear Entrada de Preguntas Frecuentes",
    },
    description: {
      en: "Convert a common customer question and its answer into a concise, clear, and helpful FAQ entry for your knowledge base.",
      tr: "Yaygın bir müşteri sorusunu ve cevabını bilgi tabanınız için kısa, net ve faydalı bir SSS girişine dönüştürün.",
      es: "Convierta una pregunta frecuente de un cliente y su respuesta en una entrada de preguntas frecuentes concisa, clara y útil para su base de conocimientos.",
    },
    prompt: {
      en: "Transform the following recurring question for {company} about {topic} and its detailed answer into a polished FAQ entry for {audience}. Ensure the language is simple, direct, and easy to scan. The question is: \"{customer_question}\". The detailed answer is: \"{detailed_answer}\".",
      tr: "{company} için {topic} hakkındaki aşağıdaki tekrarlayan soruyu ve detaylı cevabını {audience} için cilalı bir SSS girişine dönüştürün. Dilin basit, doğrudan ve göz gezdirilmesi kolay olduğundan emin olun. Soru: \"{customer_question}\". Detaylı cevap: \"{detailed_answer}\".",
      es: "Transforma la siguiente pregunta recurrente para {company} sobre {topic} y su respuesta detallada en una entrada de preguntas frecuentes pulida para {audience}. Asegúrate de que el lenguaje sea simple, directo y fácil de escanear. La pregunta es: \"{customer_question}\". La respuesta detallada es: \"{detailed_answer}\".",
    },
    placeholders: ["{company}", "{topic}", "{audience}", "{customer_question}", "{detailed_answer}"],
    estTokens: 170,
  },
  {
    id: "support-escalation",
    category: "support",
    title: {
      en: "Internal Escalation Note",
      tr: "Dahili Yükseltme Notu",
      es: "Nota de Escalada Interna",
    },
    description: {
      en: "Draft a clear and concise internal escalation note from a Level 1 to a Level 2 support agent.",
      tr: "Bir Seviye 1'den Seviye 2 destek temsilcisine açık ve özlü bir dahili yükseltme notu taslağı hazırlayın.",
      es: "Redacte una nota de escalada interna clara y concisa de un agente de soporte de Nivel 1 a uno de Nivel 2.",
    },
    prompt: {
      en: "Write an internal L1→L2 escalation note at {company} regarding {topic}. Include the customer's issue, troubleshooting steps already taken, why escalation is needed to meet the {tier} SLA by {date_range}, and any relevant customer or system details. The customer's issue is: \"{customer_issue}\".",
      tr: "{company} bünyesinde {topic} hakkında L1→L2 dahili yükseltme notu yazın. Müşterinin sorununu, halihazırda alınan sorun giderme adımlarını, {date_range} tarihine kadar {tier} SLA'sını karşılamak için neden yükseltme gerektiğini ve ilgili müşteri veya sistem ayrıntılarını ekleyin. Müşterinin sorunu: \"{customer_issue}\".",
      es: "Escribe una nota de escalada interna de N1 a N2 en {company} sobre {topic}. Incluye el problema del cliente, los pasos de solución ya realizados, por qué se necesita la escalada para cumplir con el SLA {tier} antes de {date_range}, y cualquier detalle relevante del cliente o del sistema. El problema del cliente es: \"{customer_issue}\".",
    },
    placeholders: ["{company}", "{topic}", "{tier}", "{date_range}", "{customer_issue}"],
    estTokens: 180,
  },
  {
    id: "developer-code-review",
    category: "developer",
    title: {
      en: "Secure Pull Request Review",
      tr: "Güvenli Çekme İsteği İncelemesi",
      es: "Revisión Segura de Pull Request",
    },
    description: {
      en: "Provide a thorough analysis of the pull request focusing on security, performance, and readability.",
      tr: "Çekme isteğini güvenlik, performans ve okunabilirlik açısından kapsamlı bir şekilde analiz edin.",
      es: "Realiza un análisis exhaustivo del pull request, centrándote en seguridad, rendimiento y legibilidad.",
    },
    prompt: {
      en: "As a senior engineer at {company}, review the following {topic} focusing on security vulnerabilities, performance bottlenecks, and code readability. Summarize your findings in bullet points and suggest concrete improvements.",
      tr: "Bir {company} senior mühendisi olarak, aşağıdaki {topic} güvenlik açıkları, performans darboğazları ve kod okunabilirliği açısından inceleyin. Bulgularınızı madde işaretleriyle özetleyin ve somut iyileştirme önerileri sunun.",
      es: "Como ingeniero senior en {company}, revisa el {topic} prestando atención a vulnerabilidades de seguridad, cuellos de botella de rendimiento y legibilidad del código. Resume tus hallazgos en viñetas y propone mejoras concretas.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 150,
  },
  {
    id: "developer-adr",
    category: "developer",
    title: {
      en: "Write Architecture Decision Record",
      tr: "Mimari Karar Kaydı Yaz",
      es: "Redactar Registro de Decisión Arquitectónica",
    },
    description: {
      en: "Create an ADR in the ADR-XXX format covering context, decision, and consequences for {topic} at {company}.",
      tr: "{company} içinde {topic} için bağlam, karar ve sonuçları içeren ADR-XXX formatında bir kayıt oluşturun.",
      es: "Genera un ADR en formato ADR-XXX que incluya contexto, decisión y consecuencias para {topic} en {company}.",
    },
    prompt: {
      en: "You are an architect at {company}. Write an Architecture Decision Record for {topic} using the ADR-XXX template. Include a clear context section, the chosen decision, and its short- and long-term consequences.",
      tr: "Sen {company} içinde bir mimarsın. {topic} için ADR-XXX şablonunu kullanarak bir Mimari Karar Kaydı oluştur. Bağlam, karar ve kısa ve uzun vadeli sonuçları açıkça belirt.",
      es: "Eres arquitecto en {company}. Redacta un Registro de Decisión Arquitectónica para {topic} siguiendo el formato ADR-XXX. Incluye una sección de contexto, la decisión tomada y sus consecuencias a corto y largo plazo.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 130,
  },
  {
    id: "developer-pr-description",
    category: "developer",
    title: {
      en: "Craft Polished PR Description",
      tr: "Parlatılmış PR Açıklaması Oluştur",
      es: "Crear Descripción Pulida de PR",
    },
    description: {
      en: "Transform a raw diff summary into a clear pull request description with a detailed test plan for {company}.",
      tr: "{company} için ham diff özetini net bir PR açıklamasına ve ayrıntılı bir test planına dönüştürün.",
      es: "Convierte un resumen de diff crudo en una descripción clara de PR con plan de pruebas para {company}.",
    },
    prompt: {
      en: "As a developer at {company}, take the provided diff summary for {topic} and write a polished pull request description. Include a concise overview, key changes, and a step-by-step test plan. Ensure the description is ready for reviewers.",
      tr: "Bir {company} geliştiricisi olarak, {topic} için verilen diff özetini alıp parlatılmış bir PR açıklaması yaz. Kısa bir genel bakış, önemli değişiklikler ve adım adım bir test planı ekle. Açıklamanın gözden geçirenler için hazır olduğundan emin ol.",
      es: "Como desarrollador en {company}, toma el resumen de diff de {topic} y redacta una descripción pulida del PR. Incluye una visión general concisa, los cambios clave y un plan de pruebas paso a paso. Asegúrate de que la descripción esté lista para los revisores.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 140,
  },
  {
    id: "developer-bug-repro",
    category: "developer",
    title: {
      en: "Create Minimal Repro Example",
      tr: "Minimal Tekrar Üretme Örneği Oluştur",
      es: "Crear Ejemplo Mínimo Reproducible",
    },
    description: {
      en: "Design a minimal, reproducible example that isolates the flaky test behavior for {topic} at {company}.",
      tr: "{company} içinde {topic} için hatalı testi izole eden minimal ve tekrarlanabilir bir örnek tasarlayın.",
      es: "Diseña un ejemplo mínimo y reproducible que aísle el comportamiento intermitente de la prueba para {topic} en {company}.",
    },
    prompt: {
      en: "You are a QA engineer at {company}. For the flaky test described in {topic}, build a minimal reproducible example that consistently triggers the failure. Provide the code snippet, required dependencies, and steps to run it.",
      tr: "Sen {company} içinde bir QA mühendisisin. {topic} içinde tanımlanan dalgalı testi, hatayı tutarlı şekilde tetikleyen minimal bir örnekle yeniden üret. Kod parçacığını, gerekli bağımlılıkları ve çalıştırma adımlarını sun.",
      es: "Eres ingeniero de QA en {company}. Para la prueba intermitente descrita en {topic}, crea un ejemplo mínimo reproducible que provoque consistentemente el fallo. Proporciona el fragmento de código, dependencias necesarias y pasos para ejecutarlo.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 130,
  },
  {
    id: "developer-tech-debt-audit",
    category: "developer",
    title: {
      en: "Audit Module Tech Debt",
      tr: "Modül Teknik Borç Denetimi",
      es: "Auditar Deuda Técnica del Módulo",
    },
    description: {
      en: "Examine the {topic} module at {company} to identify technical debt, prioritize issues, and suggest remediation steps.",
      tr: "{company} içinde {topic} modülünü inceleyerek teknik borçları belirleyin, önceliklendirin ve çözüm adımları önerin.",
      es: "Revisa el módulo {topic} de {company} para identificar deuda técnica, priorizar problemas y proponer pasos de remediación.",
    },
    prompt: {
      en: "As a senior developer at {company}, conduct a tech debt audit of the {topic} module. List each debt item, assess its impact, and rank fixes from high to low priority. Conclude with actionable remediation recommendations.",
      tr: "Sen {company} içinde kıdemli bir geliştiricisin, {topic} modülünün teknik borç denetimini yap. Her borç kalemini listele, etkisini değerlendir ve düzeltmeleri yüksekten düşük önceliğe göre sırala. Sonuçta uygulanabilir iyileştirme önerileri sun.",
      es: "Como desarrollador senior en {company}, realiza una auditoría de deuda técnica del módulo {topic}. Enumera cada elemento de deuda, evalúa su impacto y clasifica las correcciones de alta a baja prioridad. Concluye con recomendaciones de remediación accionables.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 150,
  },
  {
    id: "developer-api-docs",
    category: "developer",
    title: {
      en: "Generate API Documentation",
      tr: "API Belgeleri Oluştur",
      es: "Generar Documentación de API",
    },
    description: {
      en: "Create comprehensive REST and MCP API documentation from the function signatures provided for {topic} at {company}.",
      tr: "{company} için {topic} fonksiyon imzalarından kapsamlı REST ve MCP API belgeleri oluşturun.",
      es: "Genera documentación completa de API REST y MCP usando las firmas de función de {topic} en {company}.",
    },
    prompt: {
      en: "You are a technical writer at {company}. Using the list of function signatures for {topic}, produce detailed REST and MCP API documentation. Include endpoint URLs, request/response schemas, authentication details, and example calls.",
      tr: "Sen {company} içinde bir teknik yazarsın. {topic} için fonksiyon imzalarını kullanarak detaylı REST ve MCP API belgeleri oluştur. Endpoint URL'lerini, istek/yanıt şemalarını, kimlik doğrulama bilgilerini ve örnek çağrıları ekle.",
      es: "Eres redactor técnico en {company}. Con la lista de firmas de función de {topic}, genera documentación detallada de API REST y MCP. Incluye URLs de endpoint, esquemas de solicitud/respuesta, detalles de autenticación y ejemplos de llamadas.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 140,
  },
  {
    id: "content-blog-outline",
    category: "content",
    title: {
      en: "SEO Blog Outline",
      tr: "SEO Blog Taslağı",
      es: "Esquema de Blog SEO",
    },
    description: {
      en: "Generates a structured blog outline with headers and meta description for search engines.",
      tr: "Arama motorları için başlıklar ve meta açıklama içeren yapılandırılmış bir blog taslağı oluşturur.",
      es: "Genera un esquema de blog estructurado con encabezados y meta descripción para motores de búsqueda.",
    },
    prompt: {
      en: "Create a detailed SEO blog outline for {company} about {topic}. Include an H1 title, H2 and H3 subheadings, and a compelling meta description under 160 characters.",
      tr: "{company} için {topic} hakkında detaylı bir SEO blog taslağı oluştur. H1 başlığı, H2 ve H3 alt başlıkları ile 160 karakterin altında çekici bir meta açıklama ekle.",
      es: "Crea un esquema de blog SEO detallado para {company} sobre {topic}. Incluye un título H1, subtítulos H2 y H3, y una meta descripción atractiva de menos de 160 caracteres.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 120,
  },
  {
    id: "content-linkedin-post",
    category: "content",
    title: {
      en: "LinkedIn Post",
      tr: "LinkedIn Gönderisi",
      es: "Publicación de LinkedIn",
    },
    description: {
      en: "Crafts a professional LinkedIn post with an engaging hook and clear call-to-action for maximum engagement.",
      tr: "Maksimum etkileşim için çekici bir giriş ve net bir harekete geçirici mesaj içeren profesyonel bir LinkedIn gönderisi yazar.",
      es: "Crea una publicación profesional de LinkedIn con un gancho atractivo y una llamada a la acción clara para máximo engagement.",
    },
    prompt: {
      en: "Write a 250-word LinkedIn post for {company} discussing {topic}. Start with a compelling hook, provide valuable insights in the body, and end with a question to drive comments.",
      tr: "{company} için {topic} hakkında 250 kelimelik bir LinkedIn gönderisi yaz. Çekici bir girişle başla, gövdede değerli içgörüler sun ve yorumları teşvik etmek için soruyla bitir.",
      es: "Escribe una publicación de LinkedIn de 250 palabras para {company} discutiendo sobre {topic}. Comienza con un gancho convincente, proporciona información valiosa en el cuerpo y termina con una pregunta para generar comentarios.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 120,
  },
  {
    id: "content-twitter-thread",
    category: "content",
    title: {
      en: "Twitter Thread",
      tr: "Twitter Dizisi",
      es: "Hilo de Twitter",
    },
    description: {
      en: "Creates an eight-tweet thread with a strong opening and smooth transitions between each point.",
      tr: "Güçlü bir açılış ve her nokta arasında akıcı geçişler içeren sekiz tweetlik bir dizi oluşturur.",
      es: "Crea un hilo de ocho tweets con una apertura fuerte y transiciones suaves entre cada punto.",
    },
    prompt: {
      en: "Draft an 8-tweet Twitter thread for {company} about {topic}. Begin with a strong hook tweet, follow with valuable insights in tweets 2-7, and conclude with a retweet-worthy closing statement.",
      tr: "{company} için {topic} hakkında 8 tweetlik bir Twitter dizisi taslakla. Güçlü bir giriş tweetiyle başla, 2-7. tweetlerde değerli içgörüler sun ve retweet edilmeye değer bir kapanış cümlesiyle bitir.",
      es: "Redacta un hilo de Twitter de 8 tweets para {company} sobre {topic}. Comienza con un gancho fuerte, continúa con información valiosa en los tweets 2-7 y concluye con una frase final digna de retweet.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 120,
  },
  {
    id: "content-newsletter",
    category: "content",
    title: {
      en: "Weekly Newsletter",
      tr: "Haftalık Bülten",
      es: "Boletín Semanal",
    },
    description: {
      en: "Composes a newsletter section featuring three curated stories and one actionable quick tip for readers.",
      tr: "Okuyucular için üç seçilmiş haber ve uygulanabilir bir hızlı ipucu içeren bir bülten bölümü yazar.",
      es: "Compone una sección de boletín con tres historias curadas y un consejo rápido accionable para los lectores.",
    },
    prompt: {
      en: "Create a weekly newsletter section for {company} focusing on {topic}. Include three short industry news stories with brief summaries and one practical quick tip readers can implement today.",
      tr: "{company} için {topic} odaklı haftalık bir bülten bölümü oluştur. Kısa özetlerle üç kısa sektör haberi ve okuyucuların bugün uygulayabileceği pratik bir hızlı ipucu ekle.",
      es: "Crea una sección de boletín semanal para {company} enfocada en {topic}. Incluye tres historias cortas de noticias de la industria con breves resúmenes y un consejo práctico que los lectores puedan implementar hoy.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 120,
  },
  {
    id: "content-youtube-script",
    category: "content",
    title: {
      en: "YouTube Script",
      tr: "YouTube Senaryosu",
      es: "Guion de YouTube",
    },
    description: {
      en: "Writes a five-minute video script with an engaging intro, valuable content, and a compelling call-to-action.",
      tr: "Etkileyici bir giriş, değerli içerik ve ikna edici bir harekete geçirici mesaj içeren beş dakikalık bir video senaryosu yazar.",
      es: "Escribe un guion de video de cinco minutos con una introducción atractiva, contenido valioso y una llamada a la acción convincente.",
    },
    prompt: {
      en: "Write a 5-minute YouTube script for {company} about {topic}. Include a 30-second hook intro, three key value points with examples, and a strong CTA to subscribe and visit the website.",
      tr: "{company} için {topic} hakkında 5 dakikalık bir YouTube senaryosu yaz. 30 saniyelik bir giriş kancası, örneklerle üç temel değer noktası ve abone olmaları ve web sitesini ziyaret etmeleri için güçlü bir CTA ekle.",
      es: "Escribe un guion de YouTube de 5 minutos para {company} sobre {topic}. Incluye una introducción de gancho de 30 segundos, tres puntos clave de valor con ejemplos y un CTA fuerte para suscribirse y visitar el sitio web.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 120,
  },
  {
    id: "content-press-release",
    category: "content",
    title: {
      en: "Press Release",
      tr: "Basın Bülteni",
      es: "Comunicado de Prensa",
    },
    description: {
      en: "Announces a new product launch through a professional 400-word press release following standard format.",
      tr: "Standart formata uygun profesyonel 400 kelimelik bir basın bülteni aracılığıyla yeni bir ürün lansmanını duyurur.",
      es: "Anuncia el lanzamiento de un nuevo producto a través de un comunicado de prensa profesional de 400 palabras siguiendo el formato estándar.",
    },
    prompt: {
      en: "Draft a 400-word press release for {company} announcing {topic}. Follow the inverted pyramid structure with a compelling headline, dateline, lead paragraph, body quotes from executives, and boilerplate company information.",
      tr: "{company} için {topic} duyurusunu yapan 400 kelimelik bir basın bülteni taslakla. Çekici bir başlık, tarih satırı, giriş paragrafı, yöneticilerden alıntılar ve şirket bilgileri içeren ters piramit yapısını takip et.",
      es: "Redacta un comunicado de prensa de 400 palabras para {company} anunciando {topic}. Sigue la estructura de pirámide invertida con un titular atractivo, fecha de publicación, párrafo de entrada, citas del cuerpo de ejecutivos e información de la empresa.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 120,
  },
  {
    id: "finance-invoice-email",
    category: "finance",
    title: {
      en: "Friendly Invoice Reminder",
      tr: "Dostane Fatura Hatırlatması",
      es: "Recordatorio Amigable de Factura",
    },
    description: {
      en: "Draft a polite email reminding a client about an upcoming invoice payment deadline.",
      tr: "Yaklaşan fatura ödeme son tarihi için müşteriye nazikçe hatırlatma e-postası yazın.",
      es: "Redacta un correo cortés recordando a un cliente el próximo vencimiento de pago de factura.",
    },
    prompt: {
      en: "Write a friendly but professional email to {client_name} regarding invoice #{invoice_number} due on {due_date}. Remind them of the payment terms and offer assistance if they have questions about the billing details.",
      tr: "{due_date} tarihinde son ödeme tarihi olan #{invoice_number} numaralı fatura için {client_name} adlı müşteriye profesyonel ama samimi bir e-posta yazın. Ödeme koşullarını hatırlatın ve fatura detaylarıyla ilgili soruları olursa yardım teklif edin.",
      es: "Escribe un correo amigable pero profesional a {client_name} sobre la factura #{invoice_number} con vencimiento el {due_date}. Recuérdale los términos de pago y ofrece ayuda si tiene preguntas sobre los detalles de facturación.",
    },
    placeholders: ["{client_name}", "{invoice_number}", "{due_date}"],
    estTokens: 120,
  },
  {
    id: "finance-contract-clause",
    category: "finance",
    title: {
      en: "Contract Clause Draft",
      tr: "Sözleşme Maddesi Taslağı",
      es: "Borrador de Cláusula Contractual",
    },
    description: {
      en: "Generate a legal clause covering specific terms like NDA, IP rights, or payment schedules.",
      tr: "NDA, fikri mülkiyet hakları veya ödeme planları gibi belirli koşulları kapsayan yasal madde oluşturun.",
      es: "Genera una cláusula legal que cubra términos específicos como NDA, derechos de PI o calendarios de pago.",
    },
    prompt: {
      en: "Draft a {clause_type} clause for a contract with {counterparty_name}. Include standard protections for {company_name} while ensuring compliance with local jurisdiction requirements and reasonable mutual obligations.",
      tr: "{counterparty_name} ile yapılacak sözleşme için bir {clause_type} maddesi hazırlayın. Yerel yargı yetkisi gerekliliklerine uyumu sağlarken {company_name} için standart korumaları ve makul karşılıklı yükümlülükleri içerecek şekilde yazın.",
      es: "Redacta una cláusula de {clause_type} para un contrato con {counterparty_name}. Incluye protecciones estándar para {company_name} asegurando cumplimiento con requisitos de jurisdicción local y obligaciones mutuas razonables.",
    },
    placeholders: ["{clause_type}", "{counterparty_name}", "{company_name}"],
    estTokens: 135,
  },
  {
    id: "finance-gdpr-dpa",
    category: "finance",
    title: {
      en: "GDPR Data Addendum",
      tr: "GDPR Veri İşleme Eki",
      es: "Anexo de Datos GDPR",
    },
    description: {
      en: "Create a concise GDPR Data Processing Addendum for vendor agreements and compliance.",
      tr: "Tedarikçi sözleşmeleri ve uyumluluk için özlü bir GDPR Veri İşleme Eki oluşturun.",
      es: "Crea un Anexo de Tratamiento de Datos GDPR conciso para acuerdos con proveedores y cumplimiento.",
    },
    prompt: {
      en: "Write a short GDPR Data Processing Addendum for {vendor_name} who will process personal data on behalf of {company_name}. Specify data categories {data_types}, subprocessor restrictions, and breach notification timelines according to Article 28 requirements.",
      tr: "{company_name} adına kişisel verileri işleyecek olan {vendor_name} için kısa bir GDPR Veri İşleme Eki yazın. Madde 28 gerekliliklerine göre {data_types} veri kategorilerini, alt işlemci kısıtlamalarını ve ihlal bildirim sürelerini belirtin.",
      es: "Escribe un Anexo de Tratamiento de Datos GDPR corto para {vendor_name} que procesará datos personales en nombre de {company_name}. Especifica categorías de datos {data_types}, restricciones de subprocesadores y plazos de notificación de brechas según requisitos del Artículo 28.",
    },
    placeholders: ["{vendor_name}", "{company_name}", "{data_types}"],
    estTokens: 140,
  },
  {
    id: "finance-expense-category",
    category: "finance",
    title: {
      en: "Expense Categorization",
      tr: "Gider Kategorizasyonu",
      es: "Categorización de Gastos",
    },
    description: {
      en: "Sort a list of business expenses into appropriate accounting categories for monthly reporting.",
      tr: "Aylık raporlama için iş giderleri listesini uygun muhasebe kategorilerine ayırın.",
      es: "Clasifica una lista de gastos empresariales en categorías contables apropiadas para reportes mensuales.",
    },
    prompt: {
      en: "Categorize the following expenses for {month} accounting: {expense_list}. Assign each item to standard tax categories like travel, software, meals, or office supplies, and flag any items requiring receipt verification or approval limits.",
      tr: "{month} dönemi muhasebesi için şu giderleri kategorize edin: {expense_list}. Her kalemi seyahat, yazılım, yemek veya ofis malzemeleri gibi standart vergi kategorilerine atayın ve fiş doğrulaması veya onay limiti gerektiren kalemleri işaretleyin.",
      es: "Categoriza los siguientes gastos para contabilidad de {month}: {expense_list}. Asigna cada artículo a categorías fiscales estándar como viajes, software, comidas o suministros de oficina, y marca cualquier artículo que requiera verificación de recibo o límites de aprobación.",
    },
    placeholders: ["{month}", "{expense_list}"],
    estTokens: 110,
  },
  {
    id: "finance-vendor-eval",
    category: "finance",
    title: {
      en: "Vendor Evaluation",
      tr: "Tedarikçi Değerlendirmesi",
      es: "Evaluación de Proveedor",
    },
    description: {
      en: "Assess a potential vendor based on pricing, service levels, and regulatory compliance standards.",
      tr: "Fiyatlandırma, hizmet seviyeleri ve düzenleyici uyumluluk standartlarına göre potansiyel tedarikçiyi değerlendirin.",
      es: "Evalúa un proveedor potencial basándote en precios, niveles de servicio y estándares de cumplimiento regulatorio.",
    },
    prompt: {
      en: "Evaluate {vendor_name} for {service_type} procurement considering their quoted price {price_quote}, SLA uptime guarantee {sla_percentage}, and compliance certifications {certifications}. Provide a risk assessment and recommendation for contract negotiation.",
      tr: "{service_type} tedariki için {vendor_name} şirketini, verilen fiyat teklifi {price_quote}, SLA çalışma süresi garantisi {sla_percentage} ve uyumluluk sertifikaları {certifications} göz önünde bulundurarak değerlendirin. Risk değerlendirmesi ve sözleşme müzakeresi önerisi sunun.",
      es: "Evalúa a {vendor_name} para adquisición de {service_type} considerando su precio cotizado {price_quote}, garantía de uptime de SLA {sla_percentage} y certificaciones de cumplimiento {certifications}. Proporciona una evaluación de riesgos y recomendación para negociación de contrato.",
    },
    placeholders: ["{vendor_name}", "{service_type}", "{price_quote}", "{sla_percentage}", "{certifications}"],
    estTokens: 130,
  },
  {
    id: "finance-compliance-check",
    category: "finance",
    title: {
      en: "Compliance Check",
      tr: "Uyumluluk Kontrolü",
      es: "Verificación de Cumplimiento",
    },
    description: {
      en: "Perform a rapid compliance review for new features under GDPR, SOC 2, or CCPA.",
      tr: "Yeni özellikler için KVKK, GDPR veya SOC2 çerçeveleri altında hızlı bir uyumluluk incelemesi yapın.",
      es: "Realiza una revisión rápida de cumplimiento para nuevas funciones bajo RGPD, SOC 2 o CCPA.",
    },
    prompt: {
      en: "Conduct a quick compliance check for the {feature_name} update regarding {regulation_type}. Identify data handling risks, user consent requirements, and audit trail gaps that might affect {company_name}'s certification status before release.",
      tr: "{regulation_type} kapsamında {feature_name} güncellemesi için hızlı bir uyumluluk kontrolü yapın. Yayınlanmadan önce {company_name}'nin sertifikasyon durumunu etkileyebilecek veri işleme risklerini, kullanıcı onayı gerekliliklerini ve denetim izi eksikliklerini belirleyin.",
      es: "Realiza una verificación rápida de cumplimiento para la actualización de {feature_name} respecto a {regulation_type}. Identifica riesgos de manejo de datos, requisitos de consentimiento de usuario y brechas en trazabilidad de auditoría que puedan afectar el estado de certificación de {company_name} antes del lanzamiento.",
    },
    placeholders: ["{feature_name}", "{regulation_type}", "{company_name}"],
    estTokens: 125,
  },
  {
    id: "data-survey-design",
    category: "data",
    title: {
      en: "Design Customer Survey",
      tr: "Müşteri Anketi Tasarla",
      es: "Diseñar Encuesta de Clientes",
    },
    description: {
      en: "Create a concise 10-question survey mixing Likert scales and open-ended items for {company}.",
      tr: "{company} için Likert ölçeği ve açık uçlu sorular içeren 10 soruluk bir anket oluşturun.",
      es: "Cree una encuesta de diez preguntas para {company} que combine escalas Likert y preguntas abiertas.",
    },
    prompt: {
      en: "For {company}, develop a {topic} consisting of ten questions. Include five Likert-scale items ranging from Strongly Disagree to Strongly Agree, and five open-ended questions to capture detailed feedback. Ensure the survey can be completed in under five minutes and provide a brief introduction explaining its purpose.",
      tr: "{company} için bir {topic} hazırlayın. Anket, beş Likert ölçeği sorusu ve beş açık uçlu sorudan oluşmalı ve katılımcıların beş dakikadan az sürede tamamlamasını sağlamalıdır. Giriş kısmında anketin amacını kısa bir şekilde açıklayın.",
      es: "Para {company}, elabore un {topic} de diez preguntas. Incluya cinco ítems de escala Likert de 'Totalmente en desacuerdo' a 'Totalmente de acuerdo' y cinco preguntas abiertas para obtener comentarios detallados. Asegúrese de que la encuesta se complete en menos de cinco minutos y añada una breve introducción que explique su objetivo.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 130,
  },
  {
    id: "data-interview-questions",
    category: "data",
    title: {
      en: "Create Interview Questions",
      tr: "Röportaj Soruları Oluştur",
      es: "Crear Preguntas de Entrevista",
    },
    description: {
      en: "Generate eight insightful user-interview questions to explore {topic} for {company}.",
      tr: "{company} için {topic} konusunu keşfetmek amacıyla sekiz etkili kullanıcı röportaj sorusu hazırlayın.",
      es: "Genere ocho preguntas de entrevista de usuarios para descubrir {topic} en {company}.",
    },
    prompt: {
      en: "For {company}, draft a {topic} interview guide containing eight questions. Begin with warm-up queries about the user's background, then move to specific challenges, motivations, and preferred solutions. End with a reflective question that encourages participants to share unexpected insights.",
      tr: "{company} için bir {topic} röportaj rehberi hazırlayın ve sekiz soru ekleyin. İlk sorularla katılımcının geçmişi hakkında ısınma yapın, ardından zorluklar, motivasyonlar ve tercih edilen çözümler üzerine odaklanın. Son olarak, katılımcının beklenmedik içgörülerini paylaşmasını sağlayan bir yansıtma sorusu ekleyin.",
      es: "Para {company}, elabore una guía de {topic} con ocho preguntas de entrevista. Comience con preguntas de calentamiento sobre el contexto del usuario, luego indague en sus desafíos, motivaciones y soluciones preferidas. Concluya con una pregunta reflexiva que invite al participante a compartir ideas inesperadas.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 110,
  },
  {
    id: "data-funnel-interpretation",
    category: "data",
    title: {
      en: "Interpret Funnel Drop-off",
      tr: "Huni Düşüşünü Yorumla",
      es: "Interpretar Caída del Embudo",
    },
    description: {
      en: "Analyze the funnel drop-off data for {company} and suggest three plausible hypotheses.",
      tr: "{company} için huni verilerini analiz edin ve üç olası açıklama önerin.",
      es: "Analice la caída del embudo de {company} y proponga tres hipótesis plausibles.",
    },
    prompt: {
      en: "Review the recent funnel metrics for {company} and identify where the biggest drop-off occurs. Provide three testable hypotheses explaining the decline, such as user friction, messaging mismatch, or pricing concerns. Recommend a simple experiment for each hypothesis to validate its impact.",
      tr: "{company} için son huni ölçümlerini inceleyin ve en büyük düşüşün nerede olduğunu belirleyin. Kullanıcı sürtünmesi, mesaj uyumsuzluğu veya fiyat endişeleri gibi üç test edilebilir hipotez sunun. Her hipotez için etkisini doğrulamak üzere basit bir deney önerin.",
      es: "Revise las métricas del embudo reciente de {company} y detecte dónde ocurre la mayor pérdida. Proponga tres hipótesis verificables, como fricción del usuario, mensaje incoherente o preocupaciones de precio. Recomiende una prueba sencilla para cada hipótesis que permita validar su efecto.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 120,
  },
  {
    id: "data-ab-test",
    category: "data",
    title: {
      en: "Design A/B Test",
      tr: "A/B Testi Tasarla",
      es: "Diseñar Prueba A/B",
    },
    description: {
      en: "Create a complete A/B test plan for {company} focusing on {topic} with hypothesis and metrics.",
      tr: "{company} için {topic} üzerine net hipotez, birincil metrik ve örneklem büyüklüğü içeren tam bir A/B test planı oluşturun.",
      es: "Desarrolle un plan completo de prueba A/B para {company} centrado en {topic}, con hipótesis y métricas.",
    },
    prompt: {
      en: "For {company}, outline a {topic} A/B test that includes a clear hypothesis, primary metric, and required sample size. Detail the control and variant variations, test duration, and statistical significance threshold. Summarize how results will inform product decisions.",
      tr: "{company} için bir {topic} A/B testi tasarlayın; net bir hipotez, birincil metrik ve gerekli örneklem büyüklüğünü belirleyin. Kontrol ve varyant varyasyonlarını, test süresini ve istatistiksel anlamlılık eşiğini detaylandırın. Sonuçların ürün kararlarını nasıl yönlendireceğini özetleyin.",
      es: "Para {company}, elabore un test A/B de {topic} que incluya una hipótesis clara, la métrica principal y el tamaño de muestra necesario. Describa las variaciones de control y variante, la duración del test y el umbral de significancia estadística. Resuma cómo los resultados guiarán las decisiones del producto.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 130,
  },
  {
    id: "data-segmentation",
    category: "data",
    title: {
      en: "Segment Users Behaviour",
      tr: "Kullanıcı Davranışını Segmentle",
      es: "Segmentar Comportamiento de Usuarios",
    },
    description: {
      en: "Group {company} users by behaviour and suggest distinct persona names for each segment.",
      tr: "{company} kullanıcılarını davranışlarına göre gruplandırın ve her segment için ayrı persona isimleri önerin.",
      es: "Agrupe a los usuarios de {company} por comportamiento y proponga nombres de persona únicos para cada segmento.",
    },
    prompt: {
      en: "Analyze {company}'s usage data to create three behavioural segments. Assign each segment a memorable persona name that reflects its key traits. Provide a brief description of motivations, preferred features, and typical usage patterns for each persona.",
      tr: "{company}'in kullanım verilerini analiz ederek üç davranışsal segment oluşturun. Her segmente, temel özelliklerini yansıtan akılda kalıcı bir persona adı verin. Her persona için motivasyonlar, tercih edilen özellikler ve tipik kullanım kalıplarını kısa bir şekilde açıklayın.",
      es: "Analice los datos de uso de {company} para crear tres segmentos conductuales. Asigne a cada segmento un nombre de persona memorable que refleje sus rasgos principales. Proporcione una breve descripción de motivaciones, funciones preferidas y patrones de uso típicos para cada persona.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 115,
  },
  {
    id: "data-trend-report",
    category: "data",
    title: {
      en: "Generate Monthly Trend Report",
      tr: "Aylık Trend Raporu Oluştur",
      es: "Crear Informe de Tendencias Mensual",
    },
    description: {
      en: "Produce a one-page monthly trend report for {company} with a chart and bullet points.",
      tr: "{company} için bir sayfalık aylık trend raporu hazırlayın; bir grafik ve madde işaretleri ekleyin.",
      es: "Elabore un informe mensual de una página para {company} con un gráfico y viñetas.",
    },
    prompt: {
      en: "For {company}, compile a concise one-page monthly trend report focusing on {topic}. Include a clear line chart illustrating key metric changes over the past month, and accompany it with three bullet points summarizing insights, risks, and recommended actions. Keep the language executive-friendly and data-driven.",
      tr: "{company} için {topic} odaklı kısa bir aylık trend raporu derleyin. Geçen ayın ana metrik değişimlerini gösteren net bir çizgi grafiği ekleyin ve üç madde işaretiyle bulguları, riskleri ve önerilen eylemleri özetleyin. Dilin yöneticiler için uygun ve veri odaklı olmasına dikkat edin.",
      es: "Para {company}, compile un informe mensual de una página centrado en {topic}. Incluya un gráfico de líneas claro que muestre la evolución de la métrica principal durante el último mes, y acompañe con tres viñetas que resuman hallazgos, riesgos y acciones recomendadas. Mantenga el lenguaje orientado a la alta dirección y basado en datos.",
    },
    placeholders: ["{company}", "{topic}"],
    estTokens: 125,
  },
];

export function getPromptsForCategory(catId: string): PromptItem[] {
  return PROMPTS.filter((p) => p.category === catId);
}

export function searchPrompts(query: string, lang: PromptLang): PromptItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return PROMPTS;
  return PROMPTS.filter((p) =>
    p.title[lang].toLowerCase().includes(q) ||
    p.description[lang].toLowerCase().includes(q) ||
    p.prompt[lang].toLowerCase().includes(q),
  );
}

// Hero prompt IDs surfaced in the empty chat state — one item per
// category, chosen as the most universally useful first opener.
export const HERO_PROMPT_IDS = [
  "founder-weekly-review",
  "agency-client-proposal",
  "sales-cold-outreach",
  "support-ticket-triage",
  "developer-code-review",
  "content-blog-outline",
  "finance-invoice-email",
  "data-survey-design",
] as const;
