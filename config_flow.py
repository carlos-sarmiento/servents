from homeassistant import config_entries

from .const import CONF_NAME, DOMAIN


@config_entries.HANDLERS.register(DOMAIN)
class ServEntsFlowHandler(config_entries.ConfigFlow):

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(step_id="user")

        return self.async_create_entry(
            title=CONF_NAME,
            data={},
        )
