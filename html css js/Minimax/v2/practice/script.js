

const loadbtn = document.getElementById("load-btn");
const myDiv = document.getElementById("my-div");

let dataViaAPI;
let removeTag;

loadbtn.addEventListener('click', () => {

    dataViaAPI = "<h4>block1</h4><h4>block2</h4><h4>block3</h4><h4>block4</h4>";

    myDiv.innerHTML += dataViaAPI;

    myDiv.setAttribute("class", "pink-class");


});

const removebtn = document.getElementById("remove-btn");

removebtn.addEventListener('click', () => {

    removeTag = document.querySelector("h4");

    removeTag.remove();

});


let counterValue = 1;
const counterText = document.getElementById("counter");
const addBtn = document.getElementById("add-btn");
const subBtn = document.getElementById("sub-btn");


addBtn.addEventListener('click', () => {


    counterValue = parseInt(counterText.textContent);
    counterValue += 1;

    counterText.textContent = counterValue;



});

subBtn.addEventListener('click', () => {


    counterValue = parseInt(counterText.textContent);
    counterValue -= 1;

    counterText.textContent = counterValue;



});