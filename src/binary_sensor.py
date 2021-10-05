"""
The Live score binary sensor.

"""
import aiohttp
import logging
from datetime import datetime
from typing import Callable, Optional
import datetime
import voluptuous as vol
from datetime import timedelta
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_START,
)
import asyncio
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_TEAMID, DEFAULT_NAME, DOMAIN, STARTUP_MESSAGE

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)
PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_TEAMID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)
# pylint: disable=unused-argument


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info=None,
):
    """Set up the livescore sensor."""
    # Print startup message
    _LOGGER.info(STARTUP_MESSAGE)
    session = async_create_clientsession(hass)

    async_add_entities(
        [
            LivescoreBinarySensor(
                config.get(CONF_UNIQUE_ID),
                config.get(CONF_NAME),
                config.get(CONF_TEAMID),
                session,
            )
        ]
    )


class LivescoreBinarySensor(Entity):
    """Implementation of an Livescore sensor."""

    def __init__(self, unique_id: Optional[str], name: str, team_id: str, session):
        self.team_id = team_id
        """Initialize the sensor."""
        self._attr_should_poll = True
        self._attr_name = name
        self._attr_is_on = False
        self._attr_state = False
        self.session = session

        if not hasattr(self, "_score"):
            self._score = 0
        if not hasattr(self, "_starttime"):
            self._starttime = None
        # _LOGGER.info(f"Score {self._score}")
        self._attr_device_class = f"{DOMAIN}__"
        self._matchon = False

        #
        self._attr_unique_id = (
            DOMAIN + "-" + str(self.team_id) if unique_id == "__legacy__" else unique_id
        )
        self._session = session

    # @property
    # def available(self) -> bool:
    #     """Return True if entity is available."""
    #     return self._attr_is_on is not None

    # @property
    # def date(self) -> datetime:
    #     """Return the date of next match"""
    #     return self._starttime

    @staticmethod
    async def async_sleep(duration):
        """Implement async sleep"""
        await asyncio.sleep(float(duration))

    async def sleep_until(self, target, subtract=0):
        now = datetime.datetime.now()
        delta = target - now

        if delta > datetime.timedelta(0):
            await self.async_sleep(delta.total_seconds() - subtract)
            return True
        return True

    async def get_json(self, url):
        async with self.session.get(url, timeout=60) as response:
            assert response.status == 200
            return await response.json()

    async def getliveresult(self, matchid):
        url = f"https://www.fotmob.com/matchDetails?matchId={matchid}"
        resp = await self.get_json(url)
        resultdict = {
            "home": resp["header"]["teams"][0]["score"],
            "away": resp["header"]["teams"][1]["score"],
            "finished": resp["header"]["status"]["finished"],
        }
        return resultdict

    async def getmatch(self, matchid, teamid):
        """Get match information given matchid and teamid"""
        url = f"https://www.fotmob.com/matchDetails?matchId={matchid}"
        resp = await self.get_json(url)
        try:
            matchdict = {
                "matchid": resp["general"]["matchId"],
                "Starttime": resp["header"]["status"]["startTimeStr"],
                "startdate": resp["header"]["status"]["startDateStr"],
            }
        except:
            matchdict = {
                "matchid": resp["general"]["matchId"],
                "Starttime": "",
                "startdate": "",
            }

        if resp["header"]["teams"][0]["id"] == teamid:
            matchdict["homeaway"] = "home"
        else:
            matchdict["homeaway"] = "away"
        return matchdict

    async def getnextmatch(self, teamid):
        """Extract information of the next match given a teamid"""
        url = f"https://www.fotmob.com/teams?id={teamid}"
        resp = await self.get_json(url)
        nextmatch = resp["nextMatch"]
        matchdict = await self.getmatch(nextmatch["id"], teamid)
        return matchdict

    async def async_update(self):
        if self._starttime == None:
            nextmatch = await self.getnextmatch(self.team_id)
            if nextmatch["Starttime"] == "":
                self._matchon = True
            else:
                self._starttime = datetime.datetime.strptime(
                    nextmatch["startdate"] + " " + nextmatch["Starttime"],
                    "%b %d, %Y %H:%M",
                )
        nextmatch = await self.getnextmatch(self.team_id)
        result = await self.getliveresult(nextmatch["matchid"])
        if result["finished"] == False:
            if result[nextmatch["homeaway"]] > self._score:
                _LOGGER.info(
                    f"""WOOHOOO!!!!!!
                        {self.team_id} scored"""
                )
                self._score = result[nextmatch["homeaway"]]
                self._attr_state = True
                return True
            self._attr_state = False
            return True
        if self._matchon:
            nextmatch = await self.getnextmatch(self.team_id)
            if nextmatch["Starttime"] == "":
                self._matchon = True
            else:
                self._starttime = datetime.datetime.strptime(
                    nextmatch["startdate"] + " " + nextmatch["Starttime"],
                    "%b %d, %Y %H:%M",
                )
                self._matchon == False
                _LOGGER.info(
                    f"Next game is {self._starttime.date()} at {self._starttime.time()}"
                )

                _LOGGER.info(
                    """
                    Game is over
                    """
                )

        self._attr_state = False
        return True
