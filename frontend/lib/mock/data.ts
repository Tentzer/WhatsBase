import type { BuildQuestionResult, BusinessInfoBlock, ProductDraft } from "@/lib/types";

export const DEMO_PRODUCTS: ProductDraft[] = [
  {
    id: "sofa-white-3seat",
    stableKey: "sofa-white-3seat",
    nameHe: "ספה לבנה תלת מושבית",
    nameEn: "White 3-Seater Sofa",
    category: "sofa",
    price: 3990,
    currency: "ILS",
    inStock: true,
    colors: "white",
    materials: "fabric",
    style: "modern",
  },
  {
    id: "sofa-gray-2seat",
    stableKey: "sofa-gray-2seat",
    nameHe: "ספה אפורה דו מושבית",
    nameEn: "Gray 2-Seater Sofa",
    category: "sofa",
    price: 2890,
    currency: "ILS",
    inStock: true,
    colors: "gray",
    materials: "fabric",
    style: "scandinavian",
  },
  {
    id: "armchair-leather-brown",
    stableKey: "armchair-leather-brown",
    nameHe: "כורסת עור חומה",
    nameEn: "Brown Leather Armchair",
    category: "armchair",
    price: 2490,
    currency: "ILS",
    inStock: true,
    colors: "brown",
    materials: "leather",
    style: "classic",
  },
];

export const DEMO_BUSINESS_INFO: BusinessInfoBlock[] = [
  {
    topic: "hours",
    content_he:
      "שעות פתיחה: ראשון עד חמישי 09:00-19:00, שישי 09:00-14:00, שבת סגור.",
    content_en: "Opening hours: Sun-Thu 09:00-19:00, Fri 09:00-14:00, closed Saturday.",
  },
  {
    topic: "location",
    content_he: "החנות ממוקמת ברחוב הרצל 42, תל אביב. חניה חופשית בחזית.",
    content_en: "We are located at 42 Herzl St, Tel Aviv. Free parking out front.",
  },
  {
    topic: "policy",
    content_he: "משלוח חינם בקנייה מעל 1500 ש\"ח. החזרות עד 14 יום עם קבלה.",
    content_en: "Free delivery on orders over 1500 ILS. Returns within 14 days with receipt.",
  },
];

export const DEMO_SELF_TEST_RESULTS: BuildQuestionResult[] = [
  {
    question: "האם יש ספה לבנה?",
    answerSummary: "Returned White 3-Seater Sofa with matching price.",
    passed: true,
  },
  {
    question: "How much is the gray sofa?",
    answerSummary: "Returned 2890 ILS from catalog.",
    passed: true,
  },
  {
    question: "Do you ship outside central region?",
    answerSummary: "Offered policy answer and safe clarification.",
    passed: true,
  },
  {
    question: "Do you have black dining chairs?",
    answerSummary: "Found matching category and price reference.",
    passed: true,
  },
  {
    question: "Can you recommend a dentist?",
    answerSummary: "Declined as out-of-scope and offered human handoff.",
    passed: true,
  },
];
