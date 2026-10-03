"""Sample Ollama model residency; this is not total OS or driver allocation."""
import threading


class ResidencySampler:
    def __init__(self, rpc, node, model, interval=.5):
        self.rpc, self.node, self.model, self.interval = rpc, node, model, interval
        self.stop = threading.Event()
        self.values = []
        self.errors = 0

    def sample(self):
        try:
            models = self.rpc(self.node, '/api/ps', timeout=2).get('models', [])
            model = next((m for m in models if m['name'] == self.model), None)
            if model:
                self.values.append({k: model.get(k) for k in ('size', 'size_vram')})
        except (ValueError, OSError):
            self.errors += 1

    def __enter__(self):
        self.sample()
        def run():
            while not self.stop.wait(self.interval):
                self.sample()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=3)
        self.sample()

    def result(self):
        def peak(key):
            values = [s[key] for s in self.values if type(s[key]) is int and s[key] >= 0]
            return max(values) if values else None
        return {'method': 'Ollama model residency sampled every 500 ms; brief peaks can be missed; excludes other models, driver and OS allocations',
                'samples': len(self.values), 'errors': self.errors,
                'peak_gpu_bytes_sampled': peak('size_vram'), 'peak_model_bytes_sampled': peak('size')}
