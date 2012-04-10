import datetime as dt

from billy.scrape import NoDataForPeriod
from billy.scrape.events import Event, EventScraper

import lxml.html
import pytz

cal_weekly_events = "http://wapp.capitol.tn.gov/apps/schedule/WeeklyView.aspx"
cal_chamber_text = {
    "upper" : "Senate",
    "lower" : "House",
    "other" : "Joint"
}

class TNEventScraper(EventScraper):
    state = 'tn'

    _tz = pytz.timezone('US/Eastern')

    def lxmlize(self, url):
        with self.urlopen(url) as page:
            page = lxml.html.fromstring(page)
        page.make_links_absolute(url)
        return page

    def url_xpath(self, url, xpath):
        page = self.lxmlize(url)
        return page.xpath(xpath)

    def _add_agenda_main(self, url, event):
        page = self.lxmlize(url)
        # OK. We get two kinds of links. Either a list to a bunch of agendas
        # or actually a list of agendas. We can check for a <h2> at the top
        # of the generated content
        generated_content = page.xpath("//label[@id='generatedcontent']")[0]
        h2s = generated_content.xpath(".//h2")
        if len(h2s) > 0:
            return self._add_agenda_real(url, event)
        return self._add_agenda_list(url, event)

    def _add_agenda_real(self, url, event):
        trs = self.url_xpath(url, "//tr")
        for tr in trs:
            tds = tr.xpath("./*")
            billinf = tds[0].attrib['id']  # TN uses bill_ids as the id
            event.add_related_bill(billinf, type="consideration")
        event.add_source(url)
        event.add_document(url, "Agenda", type="agenda")
        return event

    def _add_agenda_list(self, url, event):
        trs = self.url_xpath(url, "//tr")
        for tr in trs:
            things = tr.xpath("./td/a")
            for thing in things:
                event = self._add_agenda_real(thing.attrib['href'], event)
        return event

    def add_agenda(self, url, name, event):
        if "CalendarMain" in url:
            return self._add_agenda_main(url, event)
        if "scheduledocs" in url:
            return event.add_document(name, url, "agenda")
        return event.add_document(name, url, "other")

    def scrape(self, chamber, session):
        chmbr = cal_chamber_text[chamber]
        tables = self.url_xpath(cal_weekly_events,
                                "//table[@class='date-table']")
        for table in tables:
            date = table.xpath("../.")[0].getprevious().text_content()
            trs = table.xpath("./tr")
            for tr in trs:
                order = [ "time", "chamber", "type", "agenda", "location",
                          "video"]

                tds = tr.xpath("./td")
                metainf = {}

                if not tds:
                    continue

                for el in range(0, len(order)):
                    metainf[order[el]] = tds[el]

                if metainf['chamber'].text_content() == chmbr:
                    self.log("Skipping event based on chamber.")
                    continue

                time = metainf['time'].text_content()
                datetime_string = "%s %s" % ( date, time )
                location = metainf['location'].text_content()
                description = metainf['type'].text_content()

                dtfmt = "%A, %B %d, %Y %I:%M %p"
                when = dt.datetime.strptime(datetime_string, dtfmt)
                event = Event(session, when, 'committee:meeting',
                              description, location=location)
                event.add_participant(description, "host", chamber=chamber)
                event.add_source(cal_weekly_events)

                agenda = metainf['agenda'].xpath(".//a")
                if len(agenda) > 0:
                    agenda = agenda
                    for doc in agenda:
                        if not doc.text_content():
                            continue
                        agenda_url = doc.attrib['href']
                        self.add_agenda(
                            agenda_url, doc.text_content(), event)
                self.save_event(event)
