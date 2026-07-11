# Customer-managed keys backing aecp_platform.secrets.KMSSecretProvider
# and the mTLS certificate authority used by aecp_platform.identity.
# Two separate keys minimum: one for secrets encryption, one for the
# internal CA's root key, so rotating one never requires rotating the
# other.
