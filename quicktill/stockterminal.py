"""Stock Terminal page"""

import time
import logging
from . import ui, td, keyboard, usestock, stocklines, user, tillconfig
from .user import load_user
from .models import StockLine, StockAnnotation, StockItem
from sqlalchemy.sql.expression import tuple_, func, null
from sqlalchemy.sql import select, not_
from sqlalchemy.orm import joinedload, undefer_group
log = logging.getLogger(__name__)

class page(ui.basicpage):
    def __init__(self, hotkeys, locations=None, user=None,
                 max_unattended_updates=None):
        ui.basicpage.__init__(self)
        self.user = user if user else load_user(tillconfig.default_user)
        self.display = 0
        self.max_unattended_updates = max_unattended_updates
        self.hotkeys = hotkeys
        self.locations = locations if locations else ['Bar']
        self.updateheader()
        self._alarm_handle = tillconfig.mainloop.add_timeout(0, self.alarm)

    def pagename(self):
        return self.user.fullname if self.user else "Stock Control"

    def drawlines(self, h):
        sl = td.s.query(StockLine).\
             filter(StockLine.location.in_(self.locations)).\
             filter(StockLine.capacity==None).\
             order_by(StockLine.name).\
             options(joinedload('stockonsale')).\
             options(joinedload('stockonsale.stocktype')).\
             options(undefer_group('qtys')).\
             all()
        f = ui.tableformatter("pl l L r rp")
        header = f("Line", "StockID", "Stock", "Used", "Remaining")
        def fl(line):
            if line.stockonsale:
                sos = line.stockonsale[0]
                return (line.name, sos.id, sos.stocktype.format(),
                        sos.used, sos.remaining)
            return (line.name, "", "", "", "")
        ml = [header] + [f(*fl(line)) for line in sl]
        y = 0
        for l in ml:
            for line in l.display(self.w):
                self.win.addstr(y, 0, line)
                y = y + 1
            if y >= h:
                break

    def drawstillage(self, h):
        sl = td.s.query(StockAnnotation)\
                 .join(StockItem)\
                 .outerjoin(StockLine)\
                 .filter(tuple_(StockAnnotation.text,StockAnnotation.time).in_(
                     select([StockAnnotation.text,
                             func.max(StockAnnotation.time)],
                            StockAnnotation.atype == 'location')\
                 .group_by(StockAnnotation.text)))\
                 .filter(StockItem.finished == None)\
                 .order_by(StockLine.name != null(), StockAnnotation.time)\
                 .options(joinedload('stockitem'))\
                 .options(joinedload('stockitem.stocktype'))\
                 .options(joinedload('stockitem.stockline'))\
                 .all()
        f = ui.tableformatter('pl l c L c lp')
        header = f("Loc", "Racked", "StockID", "Name", "BB", "Line")
        ml = [f(a.text, a.time.date().strftime("%d %b"), a.stockid,
                a.stockitem.stocktype.format(),
                a.stockitem.bestbefore or "",
                a.stockitem.stockline.name if a.stockitem.stockline
                else "") for a in sl]
        ml.insert(0, header)
        y = 0
        for l in ml:
            for line in l.display(self.w):
                self.win.addstr(y, 0, line)
                y = y + 1
            if y >= h:
                break

    def redraw(self):
        self.win.erase()
        pl = ui.lrline("Ctrl+X = Clear; Ctrl+Y = Cancel.  "
                       "Press S for stock management.  "
                       "Press U to use stock.  Press R to record waste.  "
                       "Press Enter to refresh display.  "
                       "Press A to add a stock annotation.  "
                       "Press L to lock.").display(self.w)
        y = self.h - len(pl)
        for l in pl:
            self.win.addstr(y, 0, l)
            y = y + 1
        if self.display == 0:
            self.drawlines(self.h - len(pl))
        elif self.display == 1:
            self.drawstillage(self.h - len(pl))

    def alarm(self, called_by_timer=True):
        if not called_by_timer:
            self._alarm_handle.cancel()
        self._alarm_handle = tillconfig.mainloop.add_timeout(
            2 if tillconfig.debug else 60, self.alarm)
        self.display = self.display + 1
        if self.display > 1:
            self.display = 0
        # There won't be a database session set up when we're called
        # by the timer expiring.
        if called_by_timer:
            with td.orm_session():
                if self.max_unattended_updates:
                    self.remaining_life = self.remaining_life - 1
                    if self.remaining_life < 1:
                        self.deselect()
                        return
                self.redraw()
        else:
            self.remaining_life = self.max_unattended_updates
            self.redraw()

    def keypress(self,k):
        if k in self.hotkeys:
            return self.hotkeys[k]()
        elif k == keyboard.K_CASH:
            self.alarm(called_by_timer=False)
        elif k == 'u' or k == 'U':
            stocklines.selectline(usestock.line_chosen,
                                  title="Use Stock",
                                  blurb="Select a stock line")
        else:
            ui.beep()

    def deselect(self):
        # Ensure that we're not still hanging around when we are invisible
        ui.basicpage.deselect(self)
        self._alarm_handle.cancel()
        self.dismiss()

def handle_usertoken(t,*args,**kwargs):
    """
    Called when a usertoken has been handled by the default hotkey
    handler.

    """
    u=user.user_from_token(t)
    if u is None:
        return # Should already have toasted
    return page(*args,user=u,**kwargs)
