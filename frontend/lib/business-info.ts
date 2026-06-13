import type { BusinessInfoBlock } from "@/lib/types";

export const BUSINESS_INFO_TOPIC_ORDER: BusinessInfoBlock["topic"][] = [
  "hours",
  "location",
  "policy",
  "faq",
  "other",
];

export const DEFAULT_BUSINESS_INFO_BLOCKS: BusinessInfoBlock[] = BUSINESS_INFO_TOPIC_ORDER.map(
  (topic) => ({
    topic,
    content_he: "",
    content_en: "",
  }),
);

export function normalizeBusinessInfoBlocks(
  items: BusinessInfoBlock[],
): BusinessInfoBlock[] {
  const byTopic = new Map<BusinessInfoBlock["topic"], BusinessInfoBlock>();
  for (const item of items) {
    byTopic.set(item.topic, item);
  }
  return BUSINESS_INFO_TOPIC_ORDER.map(
    (topic) => byTopic.get(topic) ?? { topic, content_he: "", content_en: "" },
  );
}
