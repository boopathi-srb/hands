"""Vendor app profiles: runtime knowledge written once per vendor product, shared by every tenant.

A discovery run only sees the happy path. What the product does when a member is missing, a session
expires, or a maintenance notice pops up is product knowledge, so it lives here and is merged into
every capability recorded against that product.
"""

from hands.profiles.model import AppProfile, ProfileLoadResult, load_profile

__all__ = ["AppProfile", "ProfileLoadResult", "load_profile"]
