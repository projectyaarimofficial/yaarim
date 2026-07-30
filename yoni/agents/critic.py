from .base import BaseAgent


class Critic(BaseAgent):
    """טרם מומש - שלד בלבד כדי שה-Router יוכל להצביע אליו."""

    def review(self, *args, **kwargs):
        raise NotImplementedError("Critic agent not implemented yet")
