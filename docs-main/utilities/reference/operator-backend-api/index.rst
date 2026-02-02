Utility Operator Backend API
****************************

The Utility Operator backend exposes a set of publicly accessible endpoints serving information 
essential to the fulfillment of the Utility Daml workflows.

It is used by the Utility UI to source reference information, such as the party
identifier of the operator, as well as the set of available instruments.

It is used by wallets and third-party apps to source off-ledger information to advance token standard
workflows (through the use of `explicit contract disclosure <https://docs.digitalasset.com/build/3.3/sdlc-howtos/applications/develop/explicit-contract-disclosure.html>`_).

.. TODO can we improve this link to always point to the latest SDK version?

Base URLs
---------

.. _operator_backend_url:

+------------------+------------------------------------------------+
| Environment      | Base URL                                       |
+==================+================================================+
| Devnet           | https://api.utilities.digitalasset-dev.com     |
+------------------+------------------------------------------------+
| Testnet          | https://api.utilities.digitalasset-staging.com |
+------------------+------------------------------------------------+
| Mainnet          | https://api.utilities.digitalasset.com         | 
+------------------+------------------------------------------------+

Token Standard endpoints
------------------------

The API specifications and base URLs for the Token Standard endpoints are documented :ref:`here <operator_backend_token_standard_endpoints>`.

Other API specifications
------------------------

The OpenAPI specification for the Utility-specific operator backend is available at the following links:

+------------------+-------------------------------------------------------------------------+
| Environment      | OpenAPI spec URL                                                        |
+==================+=========================================================================+
| Devnet           | https://api.utilities.digitalasset-dev.com/api/utilities/v0/openapi     |
+------------------+-------------------------------------------------------------------------+
| Testnet          | https://api.utilities.digitalasset-staging.com/api/utilities/v0/openapi |
+------------------+-------------------------------------------------------------------------+
| Mainnet          | https://api.utilities.digitalasset.com/api/utilities/v0/openapi         | 
+------------------+-------------------------------------------------------------------------+
