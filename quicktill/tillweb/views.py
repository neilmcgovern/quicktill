from django.http import HttpResponse,Http404
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext,Context
from django.template.loader import get_template
from django.conf import settings
from models import *
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import subqueryload_all,joinedload,subqueryload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import desc
from sqlalchemy.sql.expression import tuple_,func,null
from sqlalchemy import distinct
from quicktill.models import *

# We use this date format in templates - defined here so we don't have
# to keep repeating it.  It's available in templates as 'dtf'
dtf="Y-m-d H:i"

# This view is only used when the tillweb is integrated into another
# django-based website.
@login_required
def publist(request):
    access=Access.objects.filter(user=request.user)
    return render_to_response('tillweb/publist.html',
                              {'access':access,},
                              context_instance=RequestContext(request))

# The remainder of the view functions in this file follow a similar
# pattern.  They are kept separate rather than implemented as a
# generic view so that page-specific optimisations (the ".options()"
# clauses in the queries) can be added.  The common operations have
# been moved into the @tillweb_view decorator.

# This app can be deployed in one of two ways:

# 1. Integrated into a complete django-based website, with its own
# users and access controls.  In this case, information about which
# database to connect to and what users are permitted to do is fetched
# from the Till and Access models.  This case is used when the
# TILLWEB_SINGLE_SITE setting is absent or False.

# 2. As a standalone website, possibly with no concept of users and
# access controls.  In this case, the database, pubname and default
# access permission are read from the rest of the TILLWEB_ settings.

# Views are passed the following parameters:
# request - the Django http request object
# base - the base URL for the till's website
# user - the quicktill.models.User object if available, or 'R','M','F'
# session - sqlalchemy database session

def tillweb_view_integrated(view):
    @login_required
    def new_view(request,pubname,*args,**kwargs):
        try:
            till=Till.objects.get(slug=pubname)
        except Till.DoesNotExist:
            raise Http404
        try:
            access=Access.objects.get(user=request.user,till=till)
        except Access.DoesNotExist:
            # Pretend it doesn't exist!
            raise Http404
        try:
            session=settings.SQLALCHEMY_SESSIONS[till.database]()
        except ValueError:
            # The database doesn't exist
            raise Http404
        try:
            depts=session.query(Department).order_by(Department.id).all()
            t,d=view(request,till.get_absolute_url(),access,
                     session,*args,**kwargs)
            # pubname is used in the url;
            # object is the Till object, possibly used for a nav menu
            # till is the name of the till
            # access is 'R','M','F'
            # u is the base URL for the till website including trailing /
            defaults={'pubname':pubname,'object':till,'till':till.name,
                      'access':access.permission,'u':till.get_absolute_url(),
                      'depts':depts,'dtf':dtf}
            defaults.update(d)
            return render_to_response(
                'tillweb/'+t,defaults,
                context_instance=RequestContext(request))
        except OperationalError as oe:
            t=get_template('tillweb/operationalerror.html')
            return HttpResponse(
                t.render(RequestContext(
                        request,{'object':till,'access':access,'error':oe})),
                status=503)
        finally:
            session.close()
    return new_view

def tillweb_view_single(view):
    def new_view(request,pubname,*args,**kwargs):
        try:
            session=settings.SQLALCHEMY_SESSIONS[settings.TILLWEB_DATABASE]()
        except ValueError:
            # The database doesn't exist
            raise Http404
        till=settings.TILLWEB_PUBNAME
        access=settings.TILLWEB_DEFAULT_ACCESS
        try:
            depts=session.query(Department).order_by(Department.id).all()
            t,d=view(request,"/",access,session,*args,**kwargs)
            defaults={'pubname': "",'till':till,'access':access,
                      'depts':depts,'dtf':dtf,
                      'u':"/"} # XXX fetch base URL properly!
            defaults.update(d)
            return render_to_response(
                'tillweb/'+t,defaults,
                context_instance=RequestContext(request))
        except OperationalError as oe:
            t=get_template('tillweb/operationalerror.html')
            return HttpResponse(
                t.render(RequestContext(
                        request,{'object':till,'access':access,'error':oe})),
                status=503)
        finally:
            session.close()
    if settings.TILLWEB_LOGIN_REQUIRED:
        new_view=login_required(new_view)
    return new_view

tillweb_view=(
    tillweb_view_single if settings.TILLWEB_SINGLE_SITE
    else tillweb_view_integrated)

@tillweb_view
def pubroot(request,base,access,session):
    currentsession=Session.current(session)
    barsummary=session.query(StockLine).\
        filter(StockLine.location=="Bar").\
        order_by(StockLine.dept_id,StockLine.name).\
        options(joinedload('stockonsale')).\
        options(joinedload('stockonsale.stocktype')).\
        all()
    stillage=session.query(StockAnnotation).\
        join(StockItem).\
        outerjoin(StockLine).\
        filter(tuple_(StockAnnotation.text,StockAnnotation.time).in_(
            select([StockAnnotation.text,func.max(StockAnnotation.time)],
                   StockAnnotation.atype=='location').\
                group_by(StockAnnotation.text))).\
        filter(StockItem.finished==None).\
        order_by(StockLine.name!=null(),StockAnnotation.time).\
        options(joinedload('stockitem')).\
        options(joinedload('stockitem.stocktype')).\
        options(joinedload('stockitem.stockline')).\
        all()
    return ('index.html',
            {'currentsession':currentsession,
             'barsummary':barsummary,
             'stillage':stillage,
             })

@tillweb_view
def locationlist(request,base,access,session):
    locations=[x[0] for x in session.query(distinct(StockLine.location)).\
                   order_by(StockLine.location).all()]
    return ('locations.html',{'locations':locations})

@tillweb_view
def location(request,base,access,session,location):
    lines=session.query(StockLine).\
        filter(StockLine.location==location).\
        order_by(StockLine.dept_id,StockLine.name).\
        options(joinedload('stockonsale')).\
        options(joinedload('stockonsale.stocktype')).\
        all()
    return ('location.html',{'location':location,'lines':lines})

@tillweb_view
def session(request,base,access,session,sessionid):
    try:
        # The subqueryload_all() significantly improves the speed of loading
        # the transaction totals
        s=session.query(Session).\
            filter_by(id=int(sessionid)).\
            options(subqueryload_all('transactions.lines')).\
            one()
    except NoResultFound:
        raise Http404
    nextsession=session.query(Session).\
        filter(Session.id>s.id).\
        order_by(Session.id).\
        first()
    nextlink=base+nextsession.tillweb_url if nextsession else None
    prevsession=session.query(Session).\
        filter(Session.id<s.id).\
        order_by(desc(Session.id)).\
        first()
    prevlink=base+prevsession.tillweb_url if prevsession else None
    return ('session.html',{'session':s,'nextlink':nextlink,
                            'prevlink':prevlink})

@tillweb_view
def sessiondept(request,base,access,session,sessionid,dept):
    try:
        s=session.query(Session).filter_by(id=int(sessionid)).one()
    except NoResultFound:
        raise Http404
    try:
        dept=session.query(Department).filter_by(id=int(dept)).one()
    except NoResultFound:
        raise Http404
    translines=session.query(Transline).\
        join(Transaction).\
        filter(Transaction.sessionid==s.id).\
        filter(Transline.dept_id==dept.id).\
        order_by(Transline.time).\
        all()
    # XXX really need to joinedload stockout and related tables, but
    # there's no relation for that in the model at the moment.  Need
    # to resolve that circular dependency for creating stockout and
    # transline that mutually refer to each other.
    
    # Short version: this adds a database round-trip for every line in
    # the output.  Ick!
    return ('sessiondept.html',{'session':s,'department':dept,
                                'translines':translines})

@tillweb_view
def transaction(request,base,access,session,transid):
    try:
        t=session.query(Transaction).\
            filter_by(id=int(transid)).\
            options(subqueryload_all('lines')).\
            options(subqueryload_all('payments')).\
            one()
    except NoResultFound:
        raise Http404
    return ('transaction.html',{'transaction':t,})

@tillweb_view
def supplier(request,base,access,session,supplierid):
    try:
        s=session.query(Supplier).\
            filter_by(id=int(supplierid)).\
            one()
    except NoResultFound:
        raise Http404
    return ('supplier.html',{'supplier':s,})

@tillweb_view
def delivery(request,base,access,session,deliveryid):
    try:
        d=session.query(Delivery).\
            filter_by(id=int(deliveryid)).\
            one()
    except NoResultFound:
        raise Http404
    return ('delivery.html',{'delivery':d,})

@tillweb_view
def stocktype(request,base,access,session,stocktype_id):
    try:
        s=session.query(StockType).\
            filter_by(id=int(stocktype_id)).\
            one()
    except NoResultFound:
        raise Http404
    include_finished=request.GET.get("show_finished","false")=="true"
    items=session.query(StockItem).\
        filter(StockItem.stocktype==s).\
        order_by(desc(StockItem.id))
    if not include_finished:
        items=items.filter(StockItem.finished==None)
    items=items.all()
    return ('stocktype.html',{'stocktype':s,'items':items,
                              'include_finished':include_finished})

@tillweb_view
def stock(request,base,access,session,stockid):
    try:
        s=session.query(StockItem).\
            filter_by(id=int(stockid)).\
            options(joinedload('stocktype')).\
            options(joinedload('stocktype.department')).\
            options(joinedload('stocktype.stockline_log')).\
            options(joinedload('stocktype.stockline_log.stockline')).\
            options(joinedload('delivery')).\
            options(joinedload('delivery.supplier')).\
            options(joinedload('stockunit')).\
            options(joinedload('stockunit.unit')).\
            options(subqueryload_all('out.transline.transaction')).\
            one()
    except NoResultFound:
        raise Http404
    return ('stock.html',{'stock':s,})

@tillweb_view
def stockline(request,base,access,session,stocklineid):
    try:
        s=session.query(StockLine).\
            filter_by(id=int(stocklineid)).\
            one()
    except NoResultFound:
        raise Http404
    return ('stockline.html',{'stockline':s,})
