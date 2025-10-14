import json

from app.script_ui import controls


class StructureResultsGroup(controls.Group):
    """Single-result viewer with left/right navigation and editable cells.

    - Shows one result at a time (index).
    - Header has: [<]  Use Result  [>]
    - Each field renders: Name (TYPE) | Address | editable value input
    - Emits callbacks: on_use(index,row), on_prev(index), on_next(index), on_edit(code_index, text)
    """

    def __init__(self, on_use: callable, on_prev: callable = None, on_next: callable = None, on_edit: callable = None, **kwargs):
        super().__init__(**kwargs)
        self.on_use = on_use
        self.on_prev = on_prev
        self.on_next = on_next
        self.on_edit = on_edit
        self.headers = []  # [{'name','type'}]
        self.rows = []     # [{'base':int,'addresses':[int|None,...]}]
        self.current = 0

    def set_headers(self, headers):
        self.headers = headers or []

    def set_rows(self, rows, current: int = 0):
        self.rows = rows or []
        self.current = 0 if current < 0 else min(current, max(0, len(self.rows)-1))
        self.inner(self._render())

    def set_current(self, index: int):
        if not self.rows:
            self.current = 0
        else:
            self.current = max(0, min(index, len(self.rows)-1))
        self.inner(self._render())

    def _render(self):
        if not self.headers or not self.rows:
            return '<div></div>'

        row = self.rows[self.current]

        # Header with navigation and Use button
        left_id = f"{self.script_ids[-1]}_nav_left"
        right_id = f"{self.script_ids[-1]}_nav_right"
        use_id = f"{self.script_ids[-1]}_use"
        hdr = (
            f'<ons-row>'
            f'<ons-col width="60px" class="col ons-col-inner">'
            f'<ons-button id="{left_id}" modifier="quiet" data-function="prev" onclick="script.script_interact_button(event)"><ons-icon icon="md-chevron-left"></ons-icon></ons-button>'
            f'</ons-col>'
            f'<ons-col class="col ons-col-inner" style="text-align:center;">'
            f'<ons-button id="{use_id}" modifier="quiet" data-function="use" onclick="script.script_interact_button(event)">Use Result #{self.current+1}/{len(self.rows)}</ons-button>'
            f'</ons-col>'
            f'<ons-col width="60px" class="col ons-col-inner" style="text-align:right;">'
            f'<ons-button id="{right_id}" modifier="quiet" data-function="next" onclick="script.script_interact_button(event)"><ons-icon icon="md-chevron-right"></ons-icon></ons-button>'
            f'</ons-col>'
            f'</ons-row>'
        )

        # Fields
        body = ''
        for idx, h in enumerate(self.headers):
            name = h.get('name', '')
            tp = h.get('type', '').upper()
            addr = row.get('addresses', [None]*len(self.headers))[idx] if row else None
            addr_txt = '????????' if (addr is None or addr <= 0) else '{:X}'.format(int(addr))
            input_id = f"{self.script_ids[-1]}_cell-{idx:03d}"
            # Render input; value is unknown here; scripting layer can replace later if needed
            inp = f'<input type="text" id="{input_id}" class="text-input text-input--material text-full" ' \
                  f'data-key="{idx}" oninput="script.script_interact_value(event)" />'
            row_html = (
                f'<ons-row>'
                f'<ons-col width="35%" class="col ons-col-inner">{name} ({tp})</ons-col>'
                f'<ons-col width="25%" class="col ons-col-inner"><span class="address">{addr_txt}</span></ons-col>'
                f'<ons-col class="col ons-col-inner">{inp}</ons-col>'
                f'</ons-row>'
            )
            body += row_html

        return '<div>{}{}</div>'.format(hdr, body)

    def handle_interaction(self, _id: str, data):
        # Button interactions
        if data and data.get('type') == 'button':
            func = (data.get('data') or {}).get('function')
            if func == 'use':
                if self.on_use and self.rows:
                    self.on_use(self.get_id(), _id, {'index': self.current, 'row': self.rows[self.current]})
                return super().handle_interaction(_id, data)
            if func == 'prev':
                if self.on_prev:
                    self.on_prev(self.get_id(), _id, {'index': self.current})
                return super().handle_interaction(_id, data)
            if func == 'next':
                if self.on_next:
                    self.on_next(self.get_id(), _id, {'index': self.current})
                return super().handle_interaction(_id, data)
        # Text edits
        if data and data.get('type') == 'text':
            try:
                # id looks like input_<groupId>_cell-XYZ; dataset has data-key
                key = None
                if 'data' in data and 'key' in data['data']:
                    key = int(data['data']['key'])
            except Exception:
                key = None
            if key is not None and self.on_edit and self.rows:
                self.on_edit(self.get_id(), _id, {'index': self.current, 'key': key, 'value': data.get('value')})
        return super().handle_interaction(_id, data)
