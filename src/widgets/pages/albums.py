# albums.py

from gi.repository import Gtk, Adw, GLib, Gio
from ...integrations import get_current_integration
from ..album import AlbumButton
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/albums.ui')
class AlbumsPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneAlbumsPage'

    list_el = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()
    end_stack = Gtk.Template.Child()
    scrolledwindow = Gtk.Template.Child()
    offset = 0
    loading = False
    skipped_albums = 0
    lazy_reload = False
    reload_pending = False

    def __init__(self):
        super().__init__()
        self.scrolledwindow.get_vadjustment().connect('notify::upper', lambda va, ud: GLib.timeout_add(1000, self.check_scrollbar, va))

    def check_scrollbar(self, adjustment):
        if adjustment.get_upper() <= adjustment.get_page_size():
            threading.Thread(target=self.load_albums, daemon=True).start()

    def load(self):
        GLib.idle_add(self.load_if_empty)

    def load_if_empty(self):
        if len(list(self.list_el.list_el)) <= 1:
            self.reset_and_load()

    def reload(self):
        GLib.idle_add(self.reset_and_load)

    def reset_and_load(self):
        if self.loading:
            self.reload_pending = True
            return

        self.reload_pending = False
        self.lazy_reload = False
        self.main_stack.set_visible_child_name('loading')
        self.reset()
        self.end_stack.set_visible_child_name('loading')
        # Reserve the load before starting the worker so scrollbar callbacks wait.
        self.loading = True
        threading.Thread(target=self.load_albums, kwargs={'initial_load': True}, daemon=True).start()

    def do_showing(self):
        if self.lazy_reload:
            self.reload()

    def reset(self):
        self.offset = 0
        self.list_el.remove_all()

    def load_albums(self, initial_load=False):
        if self.loading and not initial_load:
            return

        self.loading = True
        integration = get_current_integration()
        hide_singles = Gio.Settings(schema_id="com.jeffser.Nocturne").get_value('hide-singles').unpack()
        self.skipped_albums = 0
        
        albums = integration.getAlbumList(
            list_type=self.get_tag().split('-')[1],
            size=20,
            offset=self.offset
        )

        for album_id in albums:
            should_skip = False
            if hide_singles:
                if model := integration.loaded_models.get(album_id):
                    if model.get_property('songCount') <= 1:
                        self.skipped_albums += 1
                        should_skip = True
            results = [button for button in list(self.list_el.list_el) if getattr(button, 'id', None) == album_id]
            if len(results) > 0:
                GLib.idle_add(results[0].set_visible, not should_skip)
            elif not should_skip:
                button = AlbumButton(album_id)
                GLib.idle_add(self.list_el.list_el.append, button)

        GLib.idle_add(self.end_stack.set_visible_child_name, 'end' if len(albums) - self.skipped_albums < 20 else 'loading')
        self.offset += 20
        GLib.idle_add(self.finish_loading)

    def finish_loading(self):
        self.loading = False
        if self.reload_pending:
            self.reset_and_load()
        else:
            self.update_visibility()

    @Gtk.Template.Callback()
    def scroll_edge_reached(self, scrolledwindow, pos):
        if pos == Gtk.PositionType.BOTTOM and self.end_stack.get_visible_child_name() == 'loading':
            threading.Thread(target=self.load_albums, daemon=True).start()

    def update_visibility(self):
        for row in list(self.list_el.list_el):
            if row.get_visible():
                self.main_stack.set_visible_child_name('content')
                return
        self.main_stack.set_visible_child_name('no-content')
