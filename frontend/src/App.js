import React from "react"

class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      prompt: "Welcome to Tor Weather!",
      email_1: "",
      email_2: "",
      fingerprint: "",
      get_node_down: false,
      get_version: false,
      get_low_bandwidth: false,
      get_dns_fail: false,
      node_down_grace_pd: 48,
      band_low_threshold: 20
    }

    this.handleSubmit = this.handleSubmit.bind(this);
    this.handleBandLowThresChange = this.handleBandLowThresChange.bind(this)
    this.handleNodeDownGraceTimeChange = this.handleNodeDownGraceTimeChange.bind(this)
    this.handlePrimaryEmailChange = this.handlePrimaryEmailChange.bind(this)
    this.handleReenterEmailChange = this.handleReenterEmailChange.bind(this)
    this.handleFingerprintChange = this.handleFingerprintChange.bind(this)
    this.handleGetNodeDownChange = this.handleGetNodeDownChange.bind(this)
    this.handleGetVersionChange = this.handleGetVersionChange.bind(this)
    this.handleGetLowBandwidthChange = this.handleGetLowBandwidthChange.bind(this)
    this.handleGetDNSFailChange = this.handleGetDNSFailChange.bind(this)
  }

  handleBandLowThresChange(event) {
    this.setState({
      band_low_threshold: event.target.value
    })
  }

  handleNodeDownGraceTimeChange(event) {
    this.setState({
      node_down_grace_pd: event.target.value
    })
  }

  handlePrimaryEmailChange(event) {
    this.setState({
      email_1: event.target.value
    })
  }

  handleReenterEmailChange(event) {
    this.setState({
      email_2: event.target.value
    })
  }

  handleFingerprintChange(event) {
    this.setState({
      fingerprint: event.target.value
    })
  }

  handleGetNodeDownChange(event) {
    this.setState({
      get_node_down: !this.state.get_node_down
    })
  }

  handleGetVersionChange(event) {
    this.setState({
      get_version: !this.state.get_version
    })
  }
  
  handleGetLowBandwidthChange(event) {
    this.setState({
      get_low_bandwidth: !this.state.get_low_bandwidth
    })
  }

  handleGetDNSFailChange(event) {
    this.setState({
      get_dns_fail: !this.state.get_dns_fail
    })
  }

  async handleSubmit(event) {
    event.preventDefault();

    console.log(this.state.email_1, this.state.fingerprint, this.state.get_dns_fail)

    if (this.state.email_1 !== this.state.email_2) {
      this.setState({
        prompt: "Error: email mismatch!"
      })
      return
    }

    if (this.state.fingerprint.length === 0) {
      this.setState({
        prompt: "Error: fingerprint cannot be blank!"
      })
      return
    }

    if (this.state.get_node_down === false 
      && this.state.get_version === false 
      && this.state.get_low_bandwidth === false 
      && this.state.get_dns_fail === false) {
        this.setState({
          prompt: "Error: must choose at least a choice!"
        })
        return
      }

    fetch("http://127.0.0.1:5000/", {
      method: 'POST', 
      body: JSON.stringify({
        "email": this.state.email_1,
        "fingerprint": this.state.fingerprint,
        "get_node_down": this.state.get_node_down,
        "get_version": this.state.get_version,
        "get_low_bandwidth": this.state.get_low_bandwidth,
        "get_dns_fail": this.state.get_dns_fail
      }),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
      },
    })
    .then((response) => {
      if (response.ok) {
        this.setState({
          prompt: "Congratulations, you have successfully subscribed to tor weather!"
        })
      } else {
        this.setState({
          prompt: "Oops, there's some issues. Please retry later."
        })
      }
    })
    .catch((err) => {
      console.log(err.message);
    });
  }

  render() {
    return (
      <div align='center'>
        <br/><br/>
        <font size='16'>Welcome to Tor Weather Subscription Service!</font>
        <br/><br/><br/>
        <form onSubmit={this.handleSubmit}>
          <label>Email: <input type="text" onChange={this.handlePrimaryEmailChange} /></label>
          <br/><br/>
          <label>Retype Email: <input type="text" onChange={this.handleReenterEmailChange} /></label>
          <br/><br/><br/>
          <label>Fingerprint: <input type="text" onChange={this.handleFingerprintChange} /></label>
          <br/><br/><br/>
          <label>Inform me when my relay is down:
            <input type="button" onClick={this.handleGetNodeDownChange} />
            <input type="radio" readOnly={true} checked={this.state.get_node_down} /></label>
          <br/>
          <label>Set the grace time(hour):  <input type="text" onChange={this.handleNodeDownGraceTimeChange} /></label>
          <br/><br/>
          <label>Inform me when the tor version running on my relay is outdated: 
            <input type="button" onClick={this.handleGetVersionChange} />
            <input type="radio" readOnly={true} checked={this.state.get_version}/></label>
          <br/><br/>
          <label>Inform me when the network bandwidth is lower than a threshold:  
            <input type="button" onClick={this.handleGetLowBandwidthChange} />
            <input type="radio" readOnly={true} checked={this.state.get_low_bandwidth}/></label>
          <br/>
          <label>Set the bandwidth low threshold(KB):   <input type="text" onChange={this.handleBandLowThresChange} /></label>
          <br/><br/>
          <label>Inform me when my exit node failed to resolve dns:   
            <input type="button" onClick={this.handleGetDNSFailChange} />
            <input type="radio" readOnly={true} checked={this.state.get_dns_fail}/></label>
          <br/><br/>
          <input type="submit" value="Submit" />
        </form>
        <br/><br/>
        <div>
          {this.state.prompt}
        </div>
      </div>
    )
  }
}

export default App;
