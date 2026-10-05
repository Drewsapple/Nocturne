"""Exercise the page's reload/pagination methods without a GTK display."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class AlbumReloadTest(unittest.TestCase):
    def setUp(self):
        self.idle = []
        self.workers = []
        self.requests = []
        test = self

        class Thread:
            def __init__(self, target, kwargs=None, **unused):
                self.target, self.kwargs = target, kwargs or {}

            def start(self):
                test.workers.append(lambda: self.target(**self.kwargs))

        class Stack:
            name = 'content'

            def set_visible_child_name(self, name):
                self.name = name

            def get_visible_child_name(self):
                return self.name

        class Button:
            def __init__(self, album_id):
                self.id = album_id

            def get_visible(self):
                return True

        class Wrap:
            def __init__(self):
                self.list_el = []

            def remove_all(self):
                self.list_el.clear()

        def get_albums(list_type, size, offset):
            self.requests.append((list_type, offset))
            return [str(i) for i in range(offset, min(offset + size, 60))]

        # Compile the actual methods, omitting GTK template declarations only.
        source = Path(__file__).resolve().parents[1] / 'src/widgets/pages/albums.py'
        tree = ast.parse(source.read_text())
        page_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        page_class.bases = []
        page_class.decorator_list = []
        page_class.body = [node for node in page_class.body
                           if isinstance(node, ast.FunctionDef) and node.name != '__init__']
        for method in page_class.body:
            method.decorator_list = []
        namespace = {
            'GLib': SimpleNamespace(idle_add=lambda callback, *args: self.idle.append((callback, args))),
            'Gio': SimpleNamespace(Settings=lambda **unused: SimpleNamespace(
                get_value=lambda key: SimpleNamespace(unpack=lambda: False))),
            'threading': SimpleNamespace(Thread=Thread),
            'get_current_integration': lambda: SimpleNamespace(loaded_models={}, getAlbumList=get_albums),
            'AlbumButton': Button,
            'Gtk': SimpleNamespace(PositionType=SimpleNamespace(BOTTOM='bottom')),
        }
        exec(compile(ast.fix_missing_locations(ast.Module(body=[page_class], type_ignores=[])),
                     str(source), 'exec'), namespace)
        self.page = namespace['AlbumsPage']()
        self.page.list_el = Wrap()
        self.page.main_stack = Stack()
        self.page.end_stack = Stack()
        self.page.offset = 0
        self.page.loading = False
        self.page.lazy_reload = False
        self.page.reload_pending = False
        self.page.get_tag = lambda: 'albums-newest'

    def drain_idle(self):
        while self.idle:
            callback, args = self.idle.pop(0)
            callback(*args)

    def settle(self):
        self.drain_idle()
        while self.workers:
            self.workers.pop(0)()
            self.drain_idle()

    def ids(self):
        return [button.id for button in self.page.list_el.list_el]

    def test_reload_restarts_first_page_for_each_album_category(self):
        for category in ('newest', 'starred', 'recent', 'frequent', 'random'):
            with self.subTest(category=category):
                self.setUp()
                self.page.get_tag = lambda: 'albums-' + category
                self.page.load()
                self.settle()
                self.page.scroll_edge_reached(None, 'bottom')
                self.settle()
                self.assertEqual(self.page.offset, 40)
                for _ in range(2):
                    self.page.reload()
                    self.settle()
                    self.assertEqual(self.requests[-1], (category, 0))
                    self.assertEqual(self.ids(), [str(i) for i in range(20)])
                    self.assertEqual(self.page.offset, 20)

    def test_reload_during_fetch_waits_then_discards_old_page(self):
        self.page.load()
        self.settle()
        self.page.scroll_edge_reached(None, 'bottom')
        self.workers.pop(0)()  # Fetch completed; widget appends are still queued.
        self.page.reload()
        self.settle()
        self.assertEqual(self.requests, [('newest', 0), ('newest', 20), ('newest', 0)])
        self.assertEqual(self.ids(), [str(i) for i in range(20)])

    def test_reload_before_worker_starts_and_scrollbar_cannot_duplicate_fetch(self):
        self.page.load()
        self.drain_idle()
        self.page.reload()
        self.drain_idle()
        self.page.check_scrollbar(SimpleNamespace(get_upper=lambda: 0, get_page_size=lambda: 600))
        self.settle()
        self.assertEqual(self.requests, [('newest', 0), ('newest', 0)])
        self.assertEqual(self.ids(), [str(i) for i in range(20)])
        self.assertFalse(self.page.loading)
        self.assertFalse(self.page.reload_pending)


if __name__ == '__main__':
    unittest.main()
