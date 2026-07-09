class SmartObserver:
    def __init__(self, orchestrator):
        self._orch = orchestrator
        self._prev: list[dict] = []
        self._curr: list[dict] = []
    def update(self):
        self._prev = self._curr
        self._curr = self._orch.capture_observation_structured()
    def diff_summary(self, max_chars: int=600) -> str:
        if not self._prev:
            return self.summarise(max_chars)
        prev_map = {o['uid']: o for o in self._prev}
        curr_map = {o['uid']: o for o in self._curr}
        added = [o for uid, o in curr_map.items() if uid not in prev_map]
        removed = [o for uid, o in prev_map.items() if uid not in curr_map]
        modified = [curr_map[uid] for uid in curr_map if uid in prev_map and prev_map[uid].get('shape_hash') != curr_map[uid].get('shape_hash')]
        if not (added or removed or modified):
            return '(no change)'
        parts = []
        if added:
            descs = '; '.join((self._short(o) for o in added[:3]))
            more = f' (+{len(added) - 3} more)' if len(added) > 3 else ''
            parts.append(f'+{len(added)} added: {descs}{more}')
        if removed:
            descs = '; '.join((self._short(o) for o in removed[:3]))
            parts.append(f'-{len(removed)} removed: {descs}')
        if modified:
            descs = '; '.join((self._short(o) for o in modified[:3]))
            parts.append(f'~{len(modified)} modified: {descs}')
        result = ' | '.join(parts)
        return result[:max_chars]
    def summarise(self, budget_chars: int=1500, focus_uids: set=None) -> str:
        if not self._curr:
            return 'Empty scene.'
        lines = []
        remaining = budget_chars
        def _add(line):
            nonlocal remaining
            if len(line) + 1 > remaining:
                return False
            lines.append(line)
            remaining -= len(line) + 1
            return True
        focus = focus_uids or set()
        focused = [o for o in self._curr if o['uid'] in focus]
        bodies = [o for o in self._curr if 'Body' in o.get('type', '')]
        parts = [o for o in self._curr if 'Part::' in o.get('type', '') and o['uid'] not in focus]
        rest = [o for o in self._curr if o not in focused and o not in bodies and (o not in parts)]
        for label, group, use_full in [('CHANGED', focused, True), ('Bodies', bodies, True), ('Parts', parts, False)]:
            if group:
                _add(f'{label} ({len(group)}):')
                for o in group:
                    s = f'  ✦ {self._full(o)}' if use_full else f'  {self._short(o)}'
                    if not _add(s):
                        _add(f'  … {len(group)} items (truncated)')
                        break
        if rest and remaining > 100:
            others = [self._short(o) for o in rest[:8]]
            _add(f"Other: {', '.join(others)}")
        return '\n'.join(lines) if lines else 'Empty scene.'
    @staticmethod
    def _short(o):
        tid = o.get('type', '?').split('::')[-1]
        return f"{o.get('label', o.get('name', '?'))} ({tid})"
    @staticmethod
    def _full(o):
        return o.get('summary', SmartObserver._short(o))
class PromptComposer:
    BUDGET_SYSTEM = 4000
    BUDGET_SCENE = 1200
    BUDGET_HISTORY = 600
    MAX_HISTORY_TURNS = 6
    def __init__(self, orchestrator):
        self._orch = orchestrator
        self._observer = SmartObserver(orchestrator)
    def system_prompt(self, mode: str, kb_text: str, api_corrections: str='', failure_lessons: str='') -> str:
        role = self._role_instruction(mode)
        parts = [role, kb_text]
        if api_corrections:
            parts.append(api_corrections)
        if failure_lessons:
            parts.append(failure_lessons)
        result = '\n\n'.join(parts)
        if len(result) > self.BUDGET_SYSTEM:
            result = '\n\n'.join([role, kb_text, api_corrections])
        if len(result) > self.BUDGET_SYSTEM:
            result = '\n\n'.join([role, kb_text])
        return result
    def user_prompt(self, user_input: str, mode: str, scene_summary: str='', selection_context: str='', history_entries: list=None, dependency_chain: str='', relevant_objects: str='', viewport_text: str='') -> str:
        sections = []
        if scene_summary:
            sections.append(f'### SCENE\n{scene_summary[:self.BUDGET_SCENE]}')
        if selection_context:
            sections.append(selection_context[:300])
        if relevant_objects:
            sections.append(relevant_objects[:400])
        if history_entries:
            hist = self._compress_history(history_entries[-self.MAX_HISTORY_TURNS:], budget=self.BUDGET_HISTORY)
            if hist:
                sections.append(f'### HISTORY\n{hist}')
        if dependency_chain:
            sections.append(dependency_chain[:300])
        if viewport_text:
            sections.append(viewport_text[:400])
        sections.append(f'### REQUEST\n{user_input}')
        fmt = self._output_format_reminder(mode)
        if fmt:
            sections.append(fmt)
        return '\n\n'.join(sections)
    @staticmethod
    def _role_instruction(mode: str) -> str:
        instructions = {'build': "You are an autonomous FreeCAD design agent.\nOutput a brief analysis (1-2 lines), then complete executable code.\n\nTWO-PASS FORMAT (mandatory):\n<API_PLAN>\n  list every .property = value and method() call you will use\n</API_PLAN>\n\n```python\n# complete implementation\n```\n\nThe API plan is validated against known-wrong patterns before code runs.\nEnd with: doc.recompute() and FreeCADGui.SendMsgToActiveView('ViewFit')", 'plan': 'You are the CHIEF DESIGNER.\nOutput a concise numbered plan. Each step must produce VISIBLE GEOMETRY.\nNo meta-steps (activate workbench, select, create sketch).\nDo NOT output code.', 'ask': 'You are a FreeCAD assistant. Answer concisely. No code unless asked.'}
        return instructions.get(mode, instructions['build'])
    @staticmethod
    def _output_format_reminder(mode: str) -> str:
        if mode in ('plan', 'ask'):
            return ''
        return '### OUTPUT FORMAT\n1. One-line analysis\n2. <API_PLAN>…</API_PLAN>\n3. ```python … ``` (complete)\nEnd with: doc.recompute()'
    @staticmethod
    def _compress_history(entries: list[dict], budget: int) -> str:
        lines = []
        for e in entries:
            status = '✅' if e.get('success') else '❌'
            label = (e.get('plan_label') or e.get('user', ''))[:60]
            result = e.get('result', '')[:80]
            line = f'{status} {label} → {result}'
            if sum((len(l) + 1 for l in lines)) + len(line) > budget:
                break
            lines.append(line)
        return '\n'.join(lines)
