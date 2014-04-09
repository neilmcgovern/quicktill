from __future__ import unicode_literals
import urllib,imp,textwrap,curses,sys,traceback,math,datetime
from . import ui,keyboard,td,printer,tillconfig,pdrivers
from .models import zero,penny
from decimal import Decimal

kitchenprinter=pdrivers.nullprinter(name="default_kitchenprinter")
menuurl=None

class fooditem(ui.lrline):
    def __init__(self,name,price):
        self.update(name,price)
    def update(self,name,price):
        self.name=name
        self.price=Decimal(price).quantize(penny)
        ui.lrline.__init__(self,name,tillconfig.fc(self.price)
                           if self.price!=zero else "")
    def copy(self):
        return fooditem(self.name,self.price)

class menuchoice(object):
    def __init__(self,options):
        """
        options is a list of (name,action) tuples

        """
        possible_keys=[
            keyboard.K_ONE, keyboard.K_TWO, keyboard.K_THREE,
            keyboard.K_FOUR, keyboard.K_FIVE, keyboard.K_SIX,
            keyboard.K_SEVEN, keyboard.K_EIGHT, keyboard.K_NINE,
            keyboard.K_ZERO, keyboard.K_ZEROZERO, keyboard.K_POINT]
        o=list(zip(possible_keys,options))
        self.options=o
        self.optionkeys={}
        for i in o:
            self.optionkeys[i[0]]=i
    def menu_keypress(self,itemfunc,k):
        """
        Possibly handle a keypress which will ultimately lead to the
        selection of a menu item.  When a menu item is selected, call
        itemfunc with the fooditem object as an argument.  If
        something else is selected (a submenu perhaps), invoke its
        display_menu() method and return True to indicate the keypress
        was handled.

        """
        if k in self.optionkeys:
            option=self.optionkeys[k][1]
            # If it has a display_menu method we invoke it; otherwise
            # we assume it's a food item with a price.
            if hasattr(option[1],'display_menu'):
                try:
                    option[1].display_menu(itemfunc)
                except:
                    e=traceback.format_exception(sys.exc_info()[0],sys.exc_info()[1],
                                                 sys.exc_info()[2])
                    ui.infopopup(e,title="There is a problem with the menu")
            else:
                itemfunc(fooditem(option[0],option[1]))
            return True
        return False

class simplemenu(menuchoice):
    def __init__(self,options,title=None):
        menuchoice.__init__(self,options)
        self.title=title
    def display_menu(self,itemfunc):
        # Create a popup for the menu.  When it returns an option, set
        # it up to call our menu_keypress method, probably inherited
        # from menuchoice
        il=[(key,opt[0],self.menu_keypress,(itemfunc,key))
            for key,opt in self.options]
        ui.keymenu(il,colour=ui.colour_line,title=self.title)

class subopts(object):
    """
    A menu item which can have an arbitrary number of suboptions.
    Suboptions can have a price associated with them.  It's possible
    to create classes that override the pricing method to implement
    special price policies, eg. 'Ice cream: first two scoops for 3
    pounds, then 1 pound per extra scoop'.

    """
    def __init__(self,name,itemprice,subopts,atleast=0,atmost=None,
                 connector='; ',nameconnector=': '):
        self.name=name
        self.itemprice=itemprice
        self.subopts=subopts
        self.atleast=atleast
        self.atmost=atmost
        self.nameconnector=nameconnector
        self.connector=connector
    def price(self,options):
        tot=self.itemprice
        for opt,price in options:
            tot=tot+price
        return tot
    def display_menu(self,itemfunc):
        """
        Pop up the suboptions selection dialog.  This has a 'text
        entry' area at the top which is initially filled in with the
        item name.  The suboptions are shown below.  Pressing Enter
        confirms the current entry.  Pressing a suboption number adds
        the option to the dialog.

        """
        subopts_dialog(self.name,self.subopts,self.atleast,self.atmost,
                       self.connector,self.nameconnector,self.finish,
                       itemfunc)
    def finish(self,itemfunc,chosen_options):
        total=self.price(chosen_options)
        listpart=self.connector.join([x[0] for x in chosen_options])
        if len(chosen_options)==0: name=self.name
        else: name=self.nameconnector.join([self.name,listpart])
        itemfunc(fooditem(name,total))
        
class subopts_dialog(ui.dismisspopup):
    def __init__(self,name,subopts,atleast,atmost,connector,nameconnector,
                 func,itemfunc):
        # Height: we need four lines for the "text entry" box at the top,
        # four lines for the top/bottom border, three lines for the prompt,
        # and len(subopts) lines for the suboptions list.
        h=4+4+3+len(subopts)
        self.w=68
        possible_keys=[
            (keyboard.K_ONE," 1"),
            (keyboard.K_TWO," 2"),
            (keyboard.K_THREE," 3"),
            (keyboard.K_FOUR," 4"),
            (keyboard.K_FIVE," 5"),
            (keyboard.K_SIX," 6"),
            (keyboard.K_SEVEN," 7"),
            (keyboard.K_EIGHT," 8"),
            (keyboard.K_NINE," 9"),
            (keyboard.K_ZERO," 0"),
            (keyboard.K_ZEROZERO,"00"),
            (keyboard.K_POINT,". ")]
        opts=list(zip(possible_keys,subopts))
        km={keyboard.K_CASH: (self.finish,None,False)}
        for k,so in opts:
           km[k[0]]=(self.newsubopt,(so,),False)
        ui.dismisspopup.__init__(self,h,self.w,name+" options",
                                 colour=ui.colour_line,keymap=km)
        y=9
        for k,so in opts:
           self.addstr(y,2,"%s: %s"%(k[1],so[0]))
           y=y+1
        self.ol=[]
        self.name=name
        self.atleast=atleast
        self.atmost=atmost
        self.connector=connector
        self.nameconnector=nameconnector
        self.func=func
        self.itemfunc=itemfunc
        self.redraw()
    def redraw(self):
        listpart=self.connector.join([x[0] for x in self.ol])
        if len(self.ol)>0 or self.atleast>0:
            o=self.name+self.nameconnector+listpart
        else:
            o=self.name
        w=textwrap.wrap(o,self.w-4)
        while len(w)<4: w.append("")
        if len(w)>4: self.atmost=len(self.ol)-1 # stop sillyness!
        w=["%s%s"%(x,' '*(self.w-4-len(x))) for x in w]
        y=2
        attr=curses.color_pair(ui.colour_line)|curses.A_REVERSE
        for i in w:
            self.addstr(y,2,i,attr)
            y=y+1
        self.addstr(7,2,' '*(self.w-4))
        if len(self.ol)<self.atleast:
            self.addstr(7,2,"Choose options from the list below.")
        elif len(self.ol)<self.atmost or self.atmost is None:
            self.addstr(7,2,
                            "Choose options, and press Cash/Enter to confirm.")
        else:
            self.addstr(7,2,"Press Cash/Enter to confirm.")
        self.win.move(2,2)
    def newsubopt(self,so):
        if len(self.ol)<self.atmost or self.atmost is None:
            if isinstance(so[1],float):
                self.ol.append(so)
                self.redraw()
            else:
                possible_keys=[
                    keyboard.K_ONE, keyboard.K_TWO, keyboard.K_THREE,
                    keyboard.K_FOUR, keyboard.K_FIVE, keyboard.K_SIX,
                    keyboard.K_SEVEN, keyboard.K_EIGHT, keyboard.K_NINE,
                    keyboard.K_ZERO, keyboard.K_ZEROZERO, keyboard.K_POINT]
                zz=list(zip(possible_keys,so[1]))
                il=[(key,opt[0],self.newsubopt,(opt,))
                    for key,opt in zz]
                ui.keymenu(il,colour=ui.colour_input,title=so[0])
    def finish(self):
        if len(self.ol)<self.atleast: return
        self.func(self.itemfunc,self.ol)
        self.dismiss()

def print_food_order(driver,number,ol,verbose=True,tablenumber=None,footer="",
                     transid=None,print_total=True,user=None):
    """
    This function prints a food order to the _specified_ printer.

    """
    with driver as d:
        if verbose:
            d.printline("\t%s"%tillconfig.pubname,emph=1)
            for i in tillconfig.pubaddr:
                d.printline("\t%s"%i,colour=1)
            d.printline("\tTel. %s"%tillconfig.pubnumber)
            d.printline()
        if tablenumber is not None:
            d.printline("\tTable number %s"%tablenumber,colour=1,emph=1)
            d.printline()
        if transid is not None:
            d.printline("\tTransaction %s"%transid)
            d.printline()
        if user:
            d.printline("\t%s"%user)
            d.printline()
        d.printline("\tFood order %d"%number,colour=1,emph=1)
        d.printline()
        d.printline("\t%s"%ui.formattime(datetime.datetime.now()))
        d.printline()
        tot=zero
        for item in ol:
            d.printline("%s\t\t%s"%(item.ltext,item.rtext))
            tot+=item.price
        if print_total:
            d.printline("\t\tTotal %s"%tillconfig.fc(tot),emph=1)
        d.printline()
        d.printline("\tFood order %d"%number,colour=1,emph=1)
        if tablenumber is not None:
            d.printline()
            d.printline("\tTable number %s"%tablenumber,colour=1,emph=1)
        if verbose:
            d.printline()
            d.printline("\t%s"%footer)
        else:
            d.printline()
            d.printline()


class tablenumber(ui.dismisspopup):
    """
    Request a table number and call a function with it.

    """
    def __init__(self,func):
        ui.dismisspopup.__init__(self,5,20,title="Table number",
                                 dismiss=keyboard.K_CLEAR,
                                 colour=ui.colour_line)
        self.addstr(2,2,"Table number:")
        self.numberfield=ui.editfield(
            2,16,5,validate=ui.validate_int,
            keymap={keyboard.K_CASH: (self.enter,None)})
        self.func=func
        self.numberfield.focus()
    def enter(self):
        try:
            number=int(self.numberfield.f)
        except:
            number=None
        self.dismiss()
        self.func(number)

class edititem(ui.dismisspopup):
    """
    Allow the user to edit the text of a food order item.

    """
    def __init__(self,item,func):
        ui.dismisspopup.__init__(self,5,66,title="Edit line",
                                 dismiss=keyboard.K_CLEAR,
                                 colour=ui.colour_line)
        self.addstr(2,2,"Edit this line:")
        self.linefield=ui.editfield(3,2,62,f=item.name,flen=240,
            keymap={keyboard.K_CASH: (self.enter,None)})
        self.func=func
        self.item=item
        self.linefield.focus()
    def enter(self):
        if len(self.linefield.f)>0:
            self.item.update(self.linefield.f,self.item.price)
        self.dismiss()
        self.func()

class popup(ui.basicpopup):
    def __init__(self,func,ordernumberfunc=td.foodorder_ticket,transid=None):
        if menuurl is None:
            ui.infopopup(["No menu has been set!"],title="Error")
            return
        try:
            f=urllib.urlopen(menuurl)
            g=f.read()
            f.close()
        except:
            ui.infopopup(["Unable to read the menu!"],title="Error")
            return
        try:
            self.foodmenu=imp.new_module("foodmenu")
            exec(g,self.foodmenu.__dict__)
        except:
            ui.popup_exception("There is a problem with the menu")
            return
        if "menu" not in self.foodmenu.__dict__:
            ui.infopopup(["The menu file was read succesfully, but did not "
                          "contain a menu definition."],
                         title="No menu defined")
            return
        if "staffdiscount" not in self.foodmenu.__dict__:
            ui.infopopup(["The menu file is missing a discount policy."],
                         title="Discount policy missing")
            return
        if "footer" not in self.foodmenu.__dict__:
            ui.infopopup(["The recipt footer definition is missing from "
                          "the menu file."],title="Footer missing")
            return
        if "dept" not in self.foodmenu.__dict__:
            ui.infopopup(["The department for food is missing from the "
                          "menu file."],title="Department missing")
            return
        self.staffdiscount=self.foodmenu.staffdiscount
        self.footer=self.foodmenu.footer
        self.dept=self.foodmenu.dept
        self.print_total=(
            self.foodmenu.print_total
            if "print_total" in self.foodmenu.__dict__
            else True)
        self.func=func
        self.transid=transid
        self.ordernumberfunc=ordernumberfunc
        self.h=20
        self.w=64
        kpprob=kitchenprinter.offline()
        rpprob=printer.driver.offline()
        if kpprob and rpprob:
            ui.infopopup(
                ["Both the kitchen printer and receipt printer report "
                 "problems.  You will not be able to print a food order "
                 "until these are fixed.","",
                 "Kitchen printer problem: {}".format(kpprob),
                 "Receipt printer problem: {}".format(rpprob)],
                title="Printer problems")
            return
        ui.basicpopup.__init__(self,self.h,self.w,title="Food Order",
                          colour=ui.colour_input)
        self.addstr(self.h-1,3,"Clear: abandon order   Print: finish   "
                    "Cancel:  delete item")
        # Split the top level menu into lines for display
        tlm=[""]
        labels=["1","2","3","4","5","6","7","8","9","0","00","."]
        for i in self.foodmenu.menu:
            label=labels.pop(0)
            ls="%s: %s"%(label,i[0])
            trial="%s%s%s"%(tlm[-1],('','  ')[len(tlm[-1])>0],ls)
            if len(trial)>self.w-4:
                tlm.append(ls)
            else:
                tlm[-1]=trial
        maxy=self.h-len(tlm)-2
        y=maxy+1
        for i in tlm:
            self.addstr(y,2,i)
            y=y+1
        self.ml=[] # list of chosen items
        self.order=ui.scrollable(2,2,self.w-4,maxy-1,self.ml,
                                 lastline=ui.emptyline())
        self.toplevel=menuchoice(self.foodmenu.menu)
        self.order.focus()
        if kpprob:
            ui.infopopup(
                ["The kitchen printer might not be connected or "
                 "turned on.  Please check it!","",
                 "You can continue anyway if you like; if the kitchen "
                 "printer isn't working when you try to print the "
                 "order then their copy will be printed on the "
                 "receipt printer.","",
                 "The kitchen printer says: {}".format(kpprob)],
                title="No connection to kitchen printer")
        if rpprob:
            ui.infopopup(
                ["The receipt printer is reporting a problem.  Please fix it "
                 "before trying to print the order.","",
                 "The problem is: {}".format(rpprob)],
                title="Receipt printer problem")
    def insert_item(self,item):
        self.ml.insert(self.order.cursor,item)
        self.order.cursor_down()
        self.order.redraw()
    def duplicate_item(self):
        if len(self.ml)==0: return
        if self.order.cursor>=len(self.ml):
            self.insert_item(self.ml[-1].copy())
        else:
            self.insert_item(self.ml[self.order.cursor].copy())
    def edit_item(self):
        if len(self.ml)==0: return
        if self.order.cursor_at_end(): return
        edititem(self.ml[self.order.cursor],self.order.redraw)
    def delete_item(self):
        """
        Delete the item under the cursor.  If there is no item under
        the cursor, delete the last item.  The cursor stays in the
        same place.

        """
        if len(self.ml)==0: return # Nothing to delete
        if self.order.cursor_at_end():
            self.ml.pop()
            self.order.cursor_up()
        else:
            del self.ml[self.order.cursor]
        self.order.redraw()
    def printkey(self):
        if len(self.ml)==0:
            ui.infopopup(["You haven't entered an order yet!"],title="Error")
            return
        tablenumber(self.finish)
    def finish(self,tablenumber):
        # Check on the printer before we do any work...
        rpprob=printer.driver.offline()
        if rpprob:
            ui.infopopup(
                ["The receipt printer is reporting a problem.  Please fix it "
                 "before trying to print the order.","",
                 "The problem is: {}".format(rpprob)],
                title="Receipt printer problem")
            return
        discount=sum([self.staffdiscount(tablenumber,x) for x in self.ml],zero)
        if discount>zero:
            self.ml.append(fooditem("Staff discount",zero-discount))
        tot=sum([x.price for x in self.ml],zero)
        number=self.ordernumberfunc()
        # We need to prepare a list of (dept,text,amount) tuples for
        # the register. We enter these into the register before
        # printing, so that we can avoid printing if there is a
        # register problem.
        rl=[(self.dept,x.name,x.price) for x in self.ml]
        if tablenumber is not None:
            rl.insert(0,(self.dept,"Food order %d (table %s):"%
                         (number,tablenumber),zero))
        else:
            rl.insert(0,(self.dept,"Food order %d:"%number,zero))
        r=self.func(rl) # Return values: True=success; string or None=failure
        # If r is None then a window will have been popped up telling the
        # user what's happened to their transaction.  It will have popped
        # up on top of us; we can't do anything else at this point other than
        # exit and let the user try again.
        if r==None: return
        self.dismiss()
        if r==True:
            user=ui.current_user()
            with ui.exception_guard("printing the customer copy"):
                print_food_order(printer.driver,number,self.ml,
                                 verbose=True,tablenumber=tablenumber,
                                 footer=self.footer,transid=self.transid,
                                 print_total=self.print_total)
            try:
                print_food_order(
                    kitchenprinter,number,self.ml,
                    verbose=False,tablenumber=tablenumber,
                    footer=self.footer,transid=self.transid,
                    user=user.shortname if user else None)
            except:
                e=traceback.format_exception_only(
                    sys.exc_info()[0],sys.exc_info()[1])
                try:
                    print_food_order(
                        printer.driver,number,self.ml,
                        verbose=False,tablenumber=tablenumber,
                        footer=self.footer,transid=self.transid,
                        user=user.shortname if user else None)
                except:
                    pass
                ui.infopopup(
                    ["There was a problem sending the order to the "
                     "printer in the kitchen, so the kitchen copy has been "
                     "printed here.  You must now take it to the kitchen "
                     "so that they can make it.  Check that the printer "
                     "in the kitchen has paper, is turned on, and is plugged "
                     "in to the network.","","The error message from the "
                     "printer is:"]+e,title="Kitchen printer error")
                return
        else:
            if r:
                ui.infopopup([r],title="Error")
    def keypress(self,k):
        if k==keyboard.K_CLEAR:
            # Maybe ask for confirmation?
            self.dismiss()
        elif k==keyboard.K_CANCEL:
            self.delete_item()
        elif k==keyboard.K_QUANTITY:
            self.duplicate_item()
        elif k==keyboard.K_PRINT:
            self.printkey()
        elif k==keyboard.K_CASH:
            self.edit_item()
        elif self.toplevel.menu_keypress(self.insert_item,k):
            return

class message(ui.dismisspopup):
    """
    Send a printed message to the kitchen.

    """
    def __init__(self):
        problem=kitchenprinter.offline()
        if problem:
            ui.infopopup(["There is a problem with the kitchen printer:","",
                          problem],title="Kitchen printer problem")
            return
        ui.dismisspopup.__init__(self,6,78,title="Message to kitchen",
                                 colour=ui.colour_input)
        self.addstr(2,2,"Order number:")
        self.onfield=ui.editfield(2,16,5,keymap={
                keyboard.K_CLEAR: (self.dismiss,None)})
        self.addstr(2,23,"(may be blank)")
        self.addstr(3,2,"     Message: ")
        self.messagefield=ui.editfield(
            3,16,60,flen=160,
            keymap={keyboard.K_CASH: (self.finish,None)})
        ui.map_fieldlist([self.onfield,self.messagefield])
        self.onfield.focus()
    def finish(self):
        if not self.onfield.f and not self.messagefield.f: return
        problem=kitchenprinter.offline()
        if problem:
            ui.infopopup(["There is a problem with the kitchen printer:","",
                          problem],title="Kitchen printer problem")
            return
        self.dismiss()
        try:
            with kitchenprinter as d:
                if self.onfield.f:
                    d.printline(
                        "\tMessage about order {}".format(self.onfield.f),
                        colour=1,emph=1)
                else:
                    d.printline("\tMessage",colour=1,emph=1)
                d.printline()
                d.printline("\t%s"%ui.formattime(datetime.datetime.now()))
                d.printline()
                user=ui.current_user()
                if user:
                    d.printline("\t{}".format(user.shortname))
                    d.printline()
                if self.messagefield.f:
                    d.printline("\t{}".format(self.messagefield.f))
                    d.printline()
                d.printline()
            ui.infopopup(["The message has been printed in the kitchen."],
                         title="Message sent",
                         colour=ui.colour_info,dismiss=keyboard.K_CASH)
        except:
            ui.infopopup(["There was a problem printing the message in the "
                          "kitchen.  Please try again."],
                         title="Message not sent")
