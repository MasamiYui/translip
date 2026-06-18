import type { Locale, LocaleMessages } from '../i18n/messages'
import type { ToolInfo } from '../types/atomic-tools'

export function getToolDisplayName(
  tool: ToolInfo,
  locale: Locale,
  atomicTools: LocaleMessages['atomicTools'],
): string {
  if (tool.tool_id === 'subtitle-burn' || tool.tool_id === 'subtitle-embed') {
    return atomicTools.subtitleOutput.cardTitle
  }
  return locale === 'zh-CN' ? tool.name_zh : tool.name_en
}

export function getToolDisplayDescription(
  tool: ToolInfo,
  locale: Locale,
  atomicTools: LocaleMessages['atomicTools'],
): string {
  if (tool.tool_id === 'subtitle-burn' || tool.tool_id === 'subtitle-embed') {
    return atomicTools.subtitleOutput.cardDescription
  }
  return locale === 'zh-CN' ? tool.description_zh : tool.description_en
}

export function collapseSubtitleOutputTools(tools: ToolInfo[]): ToolInfo[] {
  return tools.filter(tool => tool.tool_id !== 'subtitle-embed')
}
