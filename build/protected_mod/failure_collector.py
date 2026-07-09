import collections
import datetime
class FailureCollector:
    def __init__(self, max_per_session=200, top_n_for_prompt=5):
        self._queue = collections.deque(maxlen=max_per_session)
        self.top_n = top_n_for_prompt
    def record(self, source, exception, context=''):
        ex_type = type(exception).__name__ if exception is not None else 'UnknownError'
        ex_msg = str(exception)[:200] if exception is not None else 'No exception object provided'
        self._queue.append({'source': source, 'type': ex_type, 'message': ex_msg, 'context': context[:300], 'time': datetime.datetime.now().isoformat()})
    def top_failures(self):
        seen = {}
        for f in self._queue:
            key = (f['source'], f['type'])
            if key in seen:
                seen[key]['count'] += 1
            else:
                seen[key] = dict(f, count=1)
        ranked = sorted(seen.values(), key=lambda x: x['count'], reverse=True)
        return ranked[:self.top_n]
    def clear(self):
        self._queue.clear()
    def as_prompt_section(self):
        failures = self.top_failures()
        if not failures:
            return ''
        lines = ['### LESSONS LEARNED FROM THIS SESSION']
        for f in failures:
            lines.append(f"- {f['source']}: {f['type']} (x{f['count']}) — {f['message']}")
        return '\n'.join(lines)
