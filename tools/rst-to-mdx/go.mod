module daml.com/x/dpm-components/rst-to-mdx

go 1.22

require (
	daml.com/x/dpm-components/mintlify v0.0.0
	github.com/spf13/cobra v1.8.1
)

require (
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/spf13/pflag v1.0.5 // indirect
)

// Local path replace so go build works outside the tools/ workspace too.
// Update before publishing rst-to-mdx as a standalone artifact.
replace daml.com/x/dpm-components/mintlify => ../mintlify
